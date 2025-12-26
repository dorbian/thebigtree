//go:build !windows && !darwin && !linux

package main

import "github.com/webview/webview"

func setAlwaysOnTop(_ webview.WebView, _ bool) error { return nil }
func setClickThrough(_ webview.WebView, _ bool) error { return nil }
func minimizeWindow(_ webview.WebView) {}
