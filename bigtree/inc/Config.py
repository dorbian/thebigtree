import bigtree
import os
from configobj import ConfigObj, ConfigObjError, flatten_errors
from validate import Validator

class ConfigCheck():

    def __init__(self):
        self.configfile = bigtree.config_path
        self.config = None
        self.results = None
        self.validator = Validator()

    def config_validate(self):
        try:
            self.config = ConfigObj(self.configfile, configspec=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'spec.ini'), file_error=True)
        except (ConfigObjError, IOError) as e:
            bigtree.loch.logger.info("Could not read {0}: {1}".format(self.configfile, e))
        self.results = self.config.validate(self.validator, copy=True)
        if not self.results:
            for (section_list, key, _) in flatten_errors(self.config, self.results):
                if key is not None:
                    bigtree.loch.logger.info('The {0} key in the section {1} failed validation'.format(key, ', '.join(section_list)))
                else:
                    bigtree.loch.logger.info('The following section was missing:{0} '.format(', '.join(section_list)))

    def config_write(self):
        self.config.write()