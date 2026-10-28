"""Native CPC configuration keys; legacy entry keys remain readable."""
from .paths import data_path, auth_path

DOMAIN = "evn"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_CUSTOMER_ID = "customer_id"
CONF_REGION = "region"
CONF_NGAYDAUKY = "ngaydauky"
REGION_CPC = "CPC"
DB_PATH = str(data_path('evndata.db'))
