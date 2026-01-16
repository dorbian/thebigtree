// Overlay bootstrap.

      applyTokenFromUrl();
      applyTempTokenFromUrl();
      loadSettings();
      if (apiKeyEl.value.trim()){
        document.getElementById("loginView").classList.add("hidden");
        document.getElementById("appView").classList.remove("hidden");
        initAuthenticatedSession();
      }
      renderCard(null, [], "BING");
