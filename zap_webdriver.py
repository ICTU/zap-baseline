import logging
import string
import os
import time
import urllib
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException
from pyvirtualdisplay import Display

class ZapWebdriver:
    def __init__(self):
        self.auth_auto = False
        self.auth_display = False
        self.auth_loginUrl = ''
        self.auth_username = ''
        self.auth_password = ''
        self.auth_username_field_name = ''
        self.auth_password_field_name = ''
        self.auth_submit_field_name = ''
        self.auth_first_submit_field_name = ''
        self.auth_excludeUrls = []
        self.zap_ip = 'localhost'
        self.zap_port = 8081
        self.driver = None
        self.display = None
        self.extra_zap_params = ''
        
    def load_from_extra_zap_params(self, port, extra_zap_params):
        logging.debug ('load_from_extra_zap_params port ' + str(port))
        logging.debug ('load_from_extra_zap_params params ' + str(extra_zap_params))

        self.extra_zap_params = extra_zap_params
        self.zap_port = port
        self.auth_auto = self._get_zap_param_boolean('auth.auto')
        self.auth_display = self._get_zap_param_boolean('auth.display')
        self.auth_loginUrl = self._get_zap_param('auth.loginurl')
        self.auth_username = self._get_zap_param('auth.username')
        self.auth_password = self._get_zap_param('auth.password')
        self.auth_username_field_name = self._get_zap_param('auth.username_field')
        self.auth_password_field_name = self._get_zap_param('auth.password_field')
        self.auth_submit_field_name = self._get_zap_param('auth.submit_field')
        self.auth_first_submit_field_name = self._get_zap_param('auth.first_submit_field')
        self.auth_excludeUrls = self._get_zap_param('auth.exclude').split(',')

    def setup_zap_context(self, zap, target):
        logging.debug('Setup a new context')

        # create a new context
        contextId = zap.context.new_context('auth')

        # include everything below the target
        zap.context.include_in_context('auth', "\\Q" + target + "\\E.*")
        logging.debug('Context - included ' + target + ".*")

        # exclude all urls that end the authenticated session
        if len(self.auth_excludeUrls) == 0:
            self.auth_excludeUrls.append('(logout|uitloggen|afmelden)')

        for exclude in self.auth_excludeUrls:
            zap.context.exclude_from_context('auth', exclude)
            logging.debug ('Context - excluded ' + exclude)

        # set the context in scope
        zap.context.set_context_in_scope('auth', True)
        zap.context.set_context_in_scope('Default Context', False)

    def setup_webdriver(self, zap, target):
        logging.debug ('Setup proxy for webdriver')

        PROXY = self.zap_ip + ':' + str(self.zap_port)
        logging.debug ('PROXY: ' + PROXY)
        webdriver.DesiredCapabilities.FIREFOX['proxy'] = {
            "httpProxy":PROXY,
            "ftpProxy":PROXY,
            "sslProxy":PROXY,
            "noProxy":None,
            "proxyType":"MANUAL",
            "class":"org.openqa.selenium.Proxy",
            "autodetect":False
        }

        profile = webdriver.FirefoxProfile()
        profile.accept_untrusted_certs = True
        profile.set_preference("browser.startup.homepage_override.mstone", "ignore")
        profile.set_preference("startup.homepage_welcome_url.additional", "about:blank")

        self.display = Display(visible=self.auth_display, size=(1024, 768))
        self.display.start()

        logging.debug ('Start webdriver')
        self.driver = webdriver.Firefox(profile)
        self.driver.implicitly_wait(30)


    def login(self, zap, target):
        logging.debug('Authenticate using webdriver ' + self.auth_loginUrl)

        self.driver.get(self.auth_loginUrl)

        if self.auth_auto:
            self.auto_login(zap, target)
        else:
            self.normal_login(zap, target)

        logging.debug('Create an authenticated session')

        # Create a new session using the aquired cookies from the authentication
        zap.httpsessions.create_empty_session(target, 'auth-session')

        # add all found cookies as session cookies
        for cookie in self.driver.get_cookies():
            zap.httpsessions.set_session_token_value(target, 'auth-session', cookie['name'], cookie['value'])
            logging.debug('Cookie found: ' + cookie['name'] + ' - Value: ' + cookie['value'])

        # Mark the session as active
        zap.httpsessions.set_active_session(target, 'auth-session')

        logging.debug('Active session: ' + zap.httpsessions.active_session(target))

    def auto_login(self, zap, target):
        logging.debug ('Automatically finding login fields')

        if self.auth_username:
            # find username field
            userField = self.driver.find_element_by_xpath("(//input[(@type='text' and contains(@name,'ser')) or @type='text'])[1]")
            userField.clear()
            userField.send_keys(self.auth_username)

        # find password field
        try:
            if self.auth_password:
                passField = self.driver.find_element_by_xpath("//input[@type='password' or contains(@name,'ass')]")
                passField.clear()
                passField.send_keys(self.auth_password)

            sumbitField = self.driver.find_element_by_xpath("//*[(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='login' and (@type='submit' or @type='button')) or @type='submit' or @type='button']")
            sumbitField.click()
        except:
            logging.debug ('Did not find password field - auth in 2 steps')
            # login in two steps
            sumbitField = self.driver.find_element_by_xpath("//*[(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='login' and (@type='submit' or @type='button')) or @type='submit' or @type='button']")
            sumbitField.click()
            if self.auth_password:
                passField = self.driver.find_element_by_xpath("//input[@type='password' or contains(@name,'ass')]")
                passField.clear()
                passField.send_keys(self.auth_password)
            sumbitField = self.driver.find_element_by_xpath("//*[(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='login' and (@type='submit' or @type='button')) or @type='submit' or @type='button']")
            sumbitField.click()

    def normal_login(self, zap, target):
        if self.auth_username_field_name:
            userField = self.find_element(self.auth_username_field_name, None)
            userField.clear()
            userField.send_keys(self.auth_username)

        if self.auth_first_submit_field_name:
            self.find_element(self.auth_first_submit_field_name, "//input[@type='submit']").click()

        if self.auth_password_field_name:
            passwordField = self.find_element(self.auth_password_field_name, None)
            passwordField.clear()
            passwordField.send_keys(self.auth_password)

        self.find_element(self.auth_submit_field_name, "//input[@type='submit']").click()

    def find_element(self, name, xpath):
        element = None
        try:
            element = self.driver.find_element_by_id(name)
        except NoSuchElementException:
            try:
                element = self.driver.find_element_by_name(name)
            except NoSuchElementException:
                if xpath is None:
                    raise

                element = self.driver.find_element_by_xpath(xpath)

        return element

    def cleanup(self):
        self.driver.quit()
        self.display.stop()

    def _get_zap_param(self, key):
        for param in self.extra_zap_params:
            if param.find(key) > -1:
                return param[len(key) + 1:]
        return ''
        
    def _get_zap_param_boolean(self, key):
        for param in self.extra_zap_params:
            if param.find(key) > -1:
                return param[len(key) + 1:] in ['1', 'True', 'true']
        return False