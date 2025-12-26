//go:build windows

package main

import (
	"syscall"

	"github.com/webview/webview"
)

const (
	_gwlExstyle        = -20
	_wsExLayered       = 0x00080000
	_wsExTransparent   = 0x00000020
	_swpNoMove         = 0x0002
	_swpNoSize         = 0x0001
	_swpNoActivate     = 0x0010
	_hwndTopMost       = -1
	_hwndNoTopMost     = -2
	_swMinimize        = 6
)

var (
	_user32             = syscall.NewLazyDLL("user32.dll")
	_setWindowPos       = _user32.NewProc("SetWindowPos")
	_getWindowLongPtr   = _user32.NewProc("GetWindowLongPtrW")
	_setWindowLongPtr   = _user32.NewProc("SetWindowLongPtrW")
	_showWindow         = _user32.NewProc("ShowWindow")
)

func hwndFromWebView(w webview.WebView) uintptr {
	return uintptr(w.Window())
}

func setAlwaysOnTop(w webview.WebView, on bool) error {
	hwnd := hwndFromWebView(w)
	if hwnd == 0 {
		return nil
	}
	after := uintptr(_hwndNoTopMost)
	if on {
		after = uintptr(_hwndTopMost)
	}
	ret, _, err := _setWindowPos.Call(
		hwnd,
		after,
		0,
		0,
		0,
		0,
		_swpNoMove|_swpNoSize|_swpNoActivate,
	)
	if ret == 0 {
		return err
	}
	return nil
}

func setClickThrough(w webview.WebView, on bool) error {
	hwnd := hwndFromWebView(w)
	if hwnd == 0 {
		return nil
	}
	style, _, _ := _getWindowLongPtr.Call(hwnd, uintptr(_gwlExstyle))
	if on {
		style |= _wsExLayered | _wsExTransparent
	} else {
		style &^= _wsExTransparent
		style &^= _wsExLayered
	}
	_setWindowLongPtr.Call(hwnd, uintptr(_gwlExstyle), style)
	return nil
}

func minimizeWindow(w webview.WebView) {
	hwnd := hwndFromWebView(w)
	if hwnd == 0 {
		return
	}
	_showWindow.Call(hwnd, _swMinimize)
}
