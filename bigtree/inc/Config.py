import bigtree
import os
from configobj import ConfigObj, ConfigObjError, flatten_errors
from validate import Validator

class ConfigCheck:
    def __init__(self):
        self.configfile = bigtree.config_path
        self.config = None
        self.results = None
        self.validator = Validator()
        # path to spec.ini lives next to this file
        self._spec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec.ini")

    def config_validate(self):
        try:
            self.config = ConfigObj(self.configfile, configspec=self._spec_path, file_error=True, encoding="utf-8")
        except (ConfigObjError, IOError) as e:
            bigtree.loch.logger.info(f"Could not read {self.configfile}: {e}")
            # start with an empty config if file missing/unreadable
            self.config = ConfigObj(encoding="utf-8", configspec=self._spec_path)

        # Validate + copy default values defined in spec.ini into the live config
        self.results = self.config.validate(self.validator, copy=True)

        # Log validation failures (if any)
        if not self.results:
            for (section_list, key, _) in flatten_errors(self.config, self.results):
                if key is not None:
                    bigtree.loch.logger.info(
                        f"The {key} key in the section {', '.join(section_list)} failed validation"
                    )
                else:
                    bigtree.loch.logger.info(
                        f"The following section was missing: {', '.join(section_list)}"
                    )

        # Persist any changes
        # self.config_write()

    def config_write(self):
        self.config.write()
