//go:build darwin

package main

/*
#cgo CFLAGS: -x objective-c
#cgo LDFLAGS: -framework Cocoa
#include <Cocoa/Cocoa.h>

static void bt_set_always_on_top(void* w, int on) {
  NSWindow* win = (__bridge NSWindow*)w;
  if (!win) return;
  if (on) {
    [win setLevel:NSFloatingWindowLevel];
  } else {
    [win setLevel:NSNormalWindowLevel];
  }
}

static void bt_set_click_through(void* w, int on) {
  NSWindow* win = (__bridge NSWindow*)w;
  if (!win) return;
  [win setIgnoresMouseEvents:on ? YES : NO];
}

static void bt_minimize(void* w) {
  NSWindow* win = (__bridge NSWindow*)w;
  if (!win) return;
  [win miniaturize:nil];
}
*/
import "C"

import (
	"github.com/webview/webview"
)

func setAlwaysOnTop(w webview.WebView, on bool) error {
	if w.Window() == nil {
		return nil
	}
	if on {
		C.bt_set_always_on_top(w.Window(), 1)
	} else {
		C.bt_set_always_on_top(w.Window(), 0)
	}
	return nil
}

func setClickThrough(w webview.WebView, on bool) error {
	if w.Window() == nil {
		return nil
	}
	if on {
		C.bt_set_click_through(w.Window(), 1)
	} else {
		C.bt_set_click_through(w.Window(), 0)
	}
	return nil
}

func minimizeWindow(w webview.WebView) {
	if w.Window() == nil {
		return
	}
	C.bt_minimize(w.Window())
}
