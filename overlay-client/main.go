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
	BaseURL string `json:"base_url"`
	APIKey  string `json:"api_key"`
	Overlay bool   `json:"overlay"`
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
	w.Init(fmt.Sprintf(`
	(() => {
	  try {
	    localStorage.setItem("bt_base_url", %s);
	    localStorage.setItem("bt_api_key", %s);
	    localStorage.setItem("bt_overlay", %s);
	  } catch (e) {}
	})();`,
		jsString(cfg.BaseURL),
		jsString(cfg.APIKey),
		jsString(boolToString(cfg.Overlay)),
	))
	w.Navigate(url)
	w.Run()
}

func boolToString(v bool) string {
	if v {
		return "1"
	}
	return "0"
}
