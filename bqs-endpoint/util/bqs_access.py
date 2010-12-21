import logging, cgi, os, platform, sys

from google.appengine.api import users

class UserUtility:
	def usercredentials(self, request):
		if users.get_current_user():
			url = users.create_logout_url(request.uri)
			url_linktext = 'Logout'
		else:
			url = users.create_login_url(request.uri)
			url_linktext = 'Login'
		return url, url_linktext
	def renderuser(self, request):
		if users.get_current_user():
			return 'Logged in as: %s' %users.get_current_user().nickname()
		else:
			return "Not logged in (anonymous)."