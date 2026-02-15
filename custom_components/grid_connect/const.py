"""Constants for the Grid connect integration."""

DOMAIN = "grid_connect"

CONF_MODEL = "model"
MODEL_PC191HA = "PC191HA"
MODEL_PC191BKHA = "PC191BKHA"
MODEL_SG120HA = "SG120HA"

SUPPORTED_SMART_PLUG_MODELS: set[str] = {
    MODEL_PC191HA,
    MODEL_PC191BKHA,
    MODEL_SG120HA,
}
