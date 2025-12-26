//go:build linux

package main

/*
#cgo pkg-config: gtk+-3.0
#include <gtk/gtk.h>
#include <gdk/gdk.h>

static void bt_set_always_on_top(void* w, int on) {
  GtkWindow* win = GTK_WINDOW(w);
  if (!win) return;
  gtk_window_set_keep_above(win, on ? TRUE : FALSE);
}

static void bt_set_click_through(void* w, int on) {
  GtkWidget* widget = GTK_WIDGET(w);
  if (!widget) return;
  GdkWindow* gdk_win = gtk_widget_get_window(widget);
  if (!gdk_win) return;
  gdk_window_set_pass_through(gdk_win, on ? TRUE : FALSE);
}

static void bt_minimize(void* w) {
  GtkWindow* win = GTK_WINDOW(w);
  if (!win) return;
  gtk_window_iconify(win);
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
