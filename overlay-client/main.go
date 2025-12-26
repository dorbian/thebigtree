package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"github.com/webview/webview"
)

type Config struct {
	BaseURL      string `json:"base_url"`
	APIKey       string `json:"api_key"`
	Overlay      bool   `json:"overlay"`
	AlwaysOnTop  bool   `json:"always_on_top"`
	ClickThrough bool   `json:"click_through"`
}

func configPath() string {
	dir, err := os.UserConfigDir()
	if err != nil || dir == "" {
		home, _ := os.UserHomeDir()
		dir = filepath.Join(home, ".config")
	}
	return filepath.Join(dir, "bigtree-overlay", "config.json")
}

func loadConfig() Config {
	path := configPath()
	data, err := os.ReadFile(path)
	if err != nil {
		return Config{}
	}
	var cfg Config
	if json.Unmarshal(data, &cfg) != nil {
		return Config{}
	}
	return cfg
}

func saveConfig(cfg Config) {
	path := configPath()
	_ = os.MkdirAll(filepath.Dir(path), 0o755)
	data, _ := json.MarshalIndent(cfg, "", "  ")
	_ = os.WriteFile(path, data, 0o600)
}

func jsString(s string) string {
	b, _ := json.Marshal(s)
	return string(b)
}

func main() {
	baseFlag := flag.String("base", "", "Base URL (e.g. http://localhost:8443)")
	keyFlag := flag.String("key", "", "API key (from /auth)")
	overlayFlag := flag.Bool("overlay", false, "Enable overlay mode")
	topFlag := flag.Bool("ontop", true, "Keep window on top")
	clickFlag := flag.Bool("clickthrough", false, "Enable click-through")
	flag.Parse()

	cfg := loadConfig()
	dirty := false
	if *baseFlag != "" {
		cfg.BaseURL = *baseFlag
		dirty = true
	}
	if *keyFlag != "" {
		cfg.APIKey = *keyFlag
		dirty = true
	}
	if *overlayFlag {
		cfg.Overlay = true
		dirty = true
	}
	if *topFlag != cfg.AlwaysOnTop {
		cfg.AlwaysOnTop = *topFlag
		dirty = true
	}
	if *clickFlag != cfg.ClickThrough {
		cfg.ClickThrough = *clickFlag
		dirty = true
	}
	if cfg.BaseURL == "" {
		cfg.BaseURL = "http://localhost:8443"
	}
	if dirty {
		saveConfig(cfg)
	}

	url := fmt.Sprintf("%s/overlay", cfg.BaseURL)
	w := webview.New(false)
	defer w.Destroy()
	w.SetTitle("BigTree Overlay Client")
	w.SetSize(1200, 800, webview.HintNone)
	_ = w.Bind("btOverlayMinimize", func() {
		minimizeWindow(w)
	})
	_ = w.Bind("btOverlaySetClickThrough", func(on bool) {
		if setClickThrough(w, on) == nil {
			cfg.ClickThrough = on
			saveConfig(cfg)
		}
	})
	_ = w.Bind("btOverlaySetAlwaysOnTop", func(on bool) {
		if setAlwaysOnTop(w, on) == nil {
			cfg.AlwaysOnTop = on
			saveConfig(cfg)
		}
	})
	w.Init(fmt.Sprintf(`
	(() => {
	  try {
	    localStorage.setItem("bt_base_url", %s);
	    localStorage.setItem("bt_api_key", %s);
	    localStorage.setItem("bt_overlay", %s);
	  } catch (e) {}

	  const wrap = document.createElement("div");
	  wrap.id = "btOverlayControls";
	  wrap.style.cssText = "position:fixed;top:12px;right:12px;z-index:99999;display:flex;gap:8px;align-items:center;";

	  const btnMin = document.createElement("button");
	  btnMin.textContent = "—";
	  btnMin.title = "Minimize";
	  btnMin.style.cssText = "width:34px;height:28px;border-radius:8px;border:1px solid rgba(255,255,255,.2);background:rgba(10,20,16,.8);color:#e8f7ef;font-weight:700;cursor:pointer;";
	  btnMin.onclick = () => { if (window.btOverlayMinimize) window.btOverlayMinimize(); };

	  const btnClick = document.createElement("button");
	  btnClick.textContent = %s ? "Clickthrough: On" : "Clickthrough: Off";
	  btnClick.title = "Toggle click-through (Esc to disable)";
	  btnClick.style.cssText = "height:28px;border-radius:8px;border:1px solid rgba(255,255,255,.2);background:rgba(10,20,16,.8);color:#e8f7ef;font-weight:600;cursor:pointer;padding:0 10px;";
	  btnClick.dataset.on = %s ? "1" : "0";
	  btnClick.onclick = () => {
	    const on = btnClick.dataset.on !== "1";
	    btnClick.dataset.on = on ? "1" : "0";
	    btnClick.textContent = on ? "Clickthrough: On" : "Clickthrough: Off";
	    if (window.btOverlaySetClickThrough) window.btOverlaySetClickThrough(on);
	  };

	  document.addEventListener("keydown", (ev) => {
	    if (ev.key === "Escape" && btnClick.dataset.on === "1") {
	      btnClick.dataset.on = "0";
	      btnClick.textContent = "Clickthrough: Off";
	      if (window.btOverlaySetClickThrough) window.btOverlaySetClickThrough(false);
	    }
	  });

	  wrap.appendChild(btnClick);
	  wrap.appendChild(btnMin);
	  document.body.appendChild(wrap);
	})();`,
		jsString(cfg.BaseURL),
		jsString(cfg.APIKey),
		jsString(boolToString(cfg.Overlay)),
		func() string {
			if cfg.ClickThrough {
				return "true"
			}
			return "false"
		}(),
		func() string {
			if cfg.ClickThrough {
				return "true"
			}
			return "false"
		}(),
	))
	_ = setAlwaysOnTop(w, cfg.AlwaysOnTop)
	_ = setClickThrough(w, cfg.ClickThrough)
	w.Navigate(url)
	w.Run()
}

func boolToString(v bool) string {
	if v {
		return "1"
	}
	return "0"
}
