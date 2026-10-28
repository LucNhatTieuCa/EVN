"""Native CPC login and automatic customer discovery."""
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD, CONF_CUSTOMER_ID, CONF_REGION, REGION_CPC, CONF_NGAYDAUKY

class EVNConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self):
        self._user_input = {}
        self._linked_accounts = []
        self._connect_task = None
        self._connect_error = None
        self._pending = []

    async def async_step_user(self, user_input=None):
        return await self.async_step_credentials(user_input)

    async def async_step_credentials(self, user_input=None):
        from .paths import configure
        configure(self.hass)
        if user_input is not None:
            self._user_input = dict(user_input)
            self._connect_task = None
            self._connect_error = None
            return await self.async_step_connect()
        return self.async_show_form(step_id='credentials', data_schema=self._credentials_schema())

    async def _async_connect(self):
        from .credentials import discover_accounts, save_credentials, CredentialsError
        try:
            self._linked_accounts = await self.hass.async_add_executor_job(discover_accounts, self._user_input[CONF_USERNAME], self._user_input[CONF_PASSWORD])
            configured = {e.data.get(CONF_CUSTOMER_ID) for e in self._async_current_entries()}
            targets = [row['customer_id'] for row in self._linked_accounts]
            self._pending = [code for code in targets if code not in configured]
            if self._pending:
                await self.hass.async_add_executor_job(save_credentials, self._user_input[CONF_USERNAME], self._user_input[CONF_PASSWORD], targets)
        except CredentialsError as error:
            self._connect_error = error.code
        except Exception:
            self._connect_error = 'cannot_connect'
        finally:
            self._user_input.pop(CONF_PASSWORD, None)

    async def async_step_connect(self, user_input=None):
        if self._connect_task is None:
            self._connect_task = self.hass.async_create_task(self._async_connect())
        if not self._connect_task.done():
            return self.async_show_progress(step_id='connect', progress_action='discovering', progress_task=self._connect_task)
        return self.async_show_progress_done(next_step_id='register_customers')

    async def async_step_register_customers(self, user_input=None):
        if self._connect_error:
            return self.async_show_form(step_id='credentials', data_schema=self._credentials_schema(), errors={'base': self._connect_error})
        if not self._pending:
            return self.async_abort(reason='already_configured')
        code = self._pending[0]
        await self.async_set_unique_id(code)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=code, data={CONF_REGION: REGION_CPC, CONF_CUSTOMER_ID: code, CONF_USERNAME: code, 'data_source': 'cpc_api', CONF_NGAYDAUKY: 1, 'linked_customers': self._pending[1:]})

    def _credentials_schema(self):
        return vol.Schema({vol.Required(CONF_USERNAME): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT, autocomplete='username')), vol.Required(CONF_PASSWORD): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))})

    async def async_step_import(self, user_input):
        from .paths import configure
        configure(self.hass)
        from .official_cpc import supports
        code = str(user_input.get(CONF_CUSTOMER_ID) or '')
        if not code.startswith('PC') or not code.isalnum() or not await self.hass.async_add_executor_job(supports, code):
            return self.async_abort(reason='account_not_linked')
        await self.async_set_unique_id(code)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=code, data={CONF_REGION: REGION_CPC, CONF_CUSTOMER_ID: code, CONF_USERNAME: code, 'data_source': 'cpc_api', CONF_NGAYDAUKY: 1})

    @staticmethod
    def async_get_options_flow(config_entry):
        return EVNOptionsFlowHandler()

class EVNOptionsFlowHandler(config_entries.OptionsFlow):

    async def async_step_init(self, user_input=None):
        return await self.async_step_credentials(user_input)

    async def async_step_credentials(self, user_input=None):
        from .paths import configure
        configure(self.hass)
        from .credentials import current_username, save_credentials, CredentialsError
        from .meter_comparison import KEY
        errors = {}
        accounts = sorted({entry.data.get(CONF_CUSTOMER_ID) for entry in self.hass.config_entries.async_entries(DOMAIN) if str(entry.data.get(CONF_CUSTOMER_ID) or '').startswith('PC')})
        account = self.config_entry.data.get(CONF_CUSTOMER_ID)
        from .credentials import profile_accounts
        accounts = await self.hass.async_add_executor_job(profile_accounts, account, accounts)
        username = await self.hass.async_add_executor_job(current_username, account)
        if user_input is not None:
            username = str(user_input.get(CONF_USERNAME) or '').strip()
            try:
                await self.hass.async_add_executor_job(save_credentials, username, user_input.get(CONF_PASSWORD) or '', accounts)
            except CredentialsError as error:
                errors['base'] = error.code
            except Exception:
                errors['base'] = 'save_failed'
            else:
                for entry in self.hass.config_entries.async_entries(DOMAIN):
                    runtime = self.hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
                    coordinator = runtime.get('coordinator')
                    if coordinator and entry.data.get(CONF_CUSTOMER_ID) in accounts:
                        self.hass.async_create_task(coordinator.async_request_refresh())
                manager = self.hass.data.get(KEY)
                if manager:
                    manager.cache.clear()
                    manager.electric_cache.clear()
                    for code in set(accounts) & manager.accounts():
                        manager.schedule_refresh(code)
                return self.async_create_entry(title='', data=dict(self.config_entry.options))
        return self.async_show_form(step_id='credentials', data_schema=vol.Schema({vol.Required(CONF_USERNAME, default=username): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT, autocomplete='username')), vol.Optional(CONF_PASSWORD): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD, autocomplete='new-password'))}), errors=errors, description_placeholders={'accounts': ', '.join(accounts)})
