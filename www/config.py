configs = config_default.configs

try:
	import config_override
	configs = merge(configs, config_override.config)
except ImportError:
	pass