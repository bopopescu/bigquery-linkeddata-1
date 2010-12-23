import logging, cgi, os, platform, sys, urllib, boto, time

from google.appengine.ext import webapp
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext.webapp import template

from util.bqs_access import *
from util.bqs_global import *
from util.bqs_bqwrapper import *
from util.bqs_queryutil import *
from util.nt2csv import *

from bqs_models import *

class OverviewHandler(webapp.RequestHandler):
	def get(self):
		bqquery = BQueryModel.all().order('-date')
		squeries = bqquery.fetch(10)
		queryh = QueryHelper()
		squeries = [queryh.render_query(squery) for squery in squeries]
		currentuser = UserUtility()
		url, url_linktext = currentuser.usercredentials(self.request)
		
		templatev = {
			'querystring' : GlobalUtility.DEFAULT_QUERY_STRING,
			'hasresults' :  False,
			'queryresults' : None,
			'hassqueries' :  True if (len(squeries) > 0) else False,
			'bqueries': squeries,
			'usr' : currentuser.renderuser(self.request),
			'login_url': url,
			'login_url_linktext': url_linktext,
			'help_url' : GlobalUtility.HELP_LINK,
			'isadmin' : users.is_current_user_admin()
		}
		path = os.path.join(os.path.dirname(__file__), 'index.html')
		self.response.out.write(template.render(path, templatev))

class ExecQueryHandler(webapp.RequestHandler):
	def post(self):
		bqquery = BQueryModel.all().order('-date')
		squeries = bqquery.fetch(10)
		queryh = QueryHelper()
		squeries = [queryh.render_query(squery) for squery in squeries]
		currentuser = UserUtility()
		url, url_linktext = currentuser.usercredentials(self.request)

		# execute the query if a query string is present:
		qstr = self.request.get('querystr')
		if qstr:
			bqw = BigQueryWrapper()
			start = time.time()
			(schema, results) = bqw.execquery(qstr)
			elapsed = (time.time() - start)
			templatev = {
				'querystring' : qstr,
				'hasresults' :  True,
				'queryresults' : self.render_results(schema, results, elapsed),
				'queryschema' : schema,
				'hassqueries' :  True if (len(squeries) > 0) else False,
				'bqueries': squeries,
				'usr' : currentuser.renderuser(self.request),
				'login_url': url,
				'login_url_linktext': url_linktext,
				'help_url' : GlobalUtility.HELP_LINK,
				'isadmin' : users.is_current_user_admin()
			}
			path = os.path.join(os.path.dirname(__file__), 'index.html')
			self.response.out.write(template.render(path, templatev))
		else:
			templatev = {
				'querystring' : GlobalUtility.DEFAULT_QUERY_STRING,
				'hasresults' :  False,
				'queryresults' : None,
				'hassqueries' :  True if (len(squeries) > 0) else False,
				'bqueries': squeries,
				'usr' : currentuser.renderuser(self.request),
				'login_url': url,
				'login_url_linktext': url_linktext,
				'help_url' : GlobalUtility.HELP_LINK,
				'isadmin' : users.is_current_user_admin()
			}
			path = os.path.join(os.path.dirname(__file__), 'index.html')
			self.response.out.write(template.render(path, templatev))

	def render_results(self, schema, results, elapsed):
		
		if type(schema).__name__=='DatabaseError':
		     return '<div class="errormsg">%s</div>' %schema
		elif type(schema).__name__=='HTTPError':
		     return '<div class="errormsg">%s</div>' %schema
		
		if elapsed >= 60:
			elapsed = time.strftime('%Mmin %Ss', time.gmtime(elapsed))
		else:
			elapsed = '%.2fs' %elapsed
		
		rtable = "<div id='querystats'>It took me %s to execute this query.</div><table id='qrlist'><tr>" %elapsed
		# result columns (table head)
		for col in schema:
			rcol = "<th>%s</th>" %col[0]
			rtable = rtable + rcol
 		rtable = rtable + "</tr>"
		# result data 
		for cr, row in enumerate(results):
	 		rtable = rtable + "<tr>"
			for ci, col in enumerate(schema):
				if cr%2:
					rrow = "<td>%s</td>" %row[ci]
				else:
					rrow = "<td class='odd'>%s</td>" %row[ci]
				rtable = rtable + rrow
 			rtable = rtable + "</tr>"
 		rtable = rtable + "</table>"
		return rtable
	
class SaveQueryHandler(webapp.RequestHandler):
	def post(self):
		try:
			logging.info("Saving query ...")
			bqm = BQueryModel()
			if users.get_current_user():
				bqm.author = users.get_current_user()
			bqm.querystr = self.request.get('querystr')
			qkey = bqm.put()
			self.response.out.write('saved query.')
		except Error:
			self.error(500)
	
class DeleteQueryHandler(webapp.RequestHandler):
	def post(self):
		try:
			if users.is_current_user_admin():
				logging.info("Deleting query ...")
				bqk = self.request.get('querid')
				db.delete(db.Key(bqk))
				self.response.out.write('deleted query.')
			else:
				self.response.out.write('you are not allowed to delete a query!')
		except Error:
			self.error(500)


class ImportHandler(webapp.RequestHandler):
	def get(self):
		upload_url = blobstore.create_upload_url('/upload')
		datasetlinks = self.listds()
		uploadlinks = self.listuploads()
		currentuser = UserUtility()
		url, url_linktext = currentuser.usercredentials(self.request)
		templatev = {
			'upload_url': upload_url,
			'datasetlinks': datasetlinks,
			'datasetstats': self.render_dataset_stats(),
			'uploadlinks': uploadlinks,
			'login_url': url,
			'login_url_linktext': url_linktext,
			'help_url' : GlobalUtility.HELP_LINK,
			'isadmin' : users.is_current_user_admin()
		}
		path = os.path.join(os.path.dirname(__file__), 'import.html')
		self.response.out.write(template.render(path, templatev))

	def listuploads(self):
		uploadfquery = NTriplesFileModel.all().order('fname')
		#logging.info("Available files:")
		#for uploadf in uploadfquery:
		#	logging.info(uploadf.fname)
		return uploadfquery
		
	def listds(self):
		gsh = GSHelper()
		gsh.gs_init()
		uri = boto.storage_uri(GlobalUtility.IMPORT_BUCKET, "gs")
		buckets = uri.get_bucket()
		return [self.render_dataset(bobject) for bobject in buckets]

	def render_dataset_stats(self):
		bqw = BigQueryWrapper()
		numtriples = bqw.numtriples()
		return '<div id="dsstats">Triple count: %s</div>' %numtriples 
		
	def render_dataset(self, bobject):
		if not bobject.name.find(GlobalUtility.RDFTABLE_OBJECT) >= 0: # only process stuff from import object, not in the table object		
			if not bobject.name.find(GlobalUtility.METADATA_POSTFIX) >= 0: # only process non-metadata files
				absbucketURI = "/".join([GlobalUtility.GOOGLE_STORAGE_BASE_URI, GlobalUtility.IMPORT_BUCKET, bobject.name])
				#logging.info("Looking at import bucket: %s " %absbucketURI)
				dataset_name = bobject.name.split("/")[1].split(".")[0] # abc/xxx.nt -> xxx
				graph_uri = self.get_metadata(bobject, 'graphURI')
				#logging.info("Got %s from graph %s in Google Storage" %(bobject.name, graph_uri))
				bobjectlink = '<td>%s</td><td><a href="%s" target="_new">gs://%s</a></td><td>%s</td>' %(dataset_name, absbucketURI, "/".join([GlobalUtility.IMPORT_BUCKET, bobject.name]), graph_uri)
				return bobjectlink
			else:
				return ""
		return ""

	def get_metadata(self, bobject, m_key):
		gsm_target = "/".join([GlobalUtility.IMPORT_BUCKET, bobject.name.split(".")[0]])
		gsm_target = ".".join([gsm_target, GlobalUtility.METADATA_POSTFIX])
		#logging.info("Looking for metadata at %s " %gsm_target)
		try:
			gskey = boto.storage_uri(gsm_target, "gs")
			ometadata = gskey.get_contents_as_string()
			graph_uri = ometadata.split("=")[1]
			#logging.info("Got metadata %s in Google Storage" %ometadata)
		except:
			graph_uri = GlobalUtility.DEFAULT_GRAPH_URI
		return graph_uri

	def post(self):
		pass

class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):
	def post(self):
		uploads = self.get_uploads('ntfile')
		blob_info = uploads[0]
		# check if filename already exists and if not, upload it
		if not self.file_exists(blob_info.filename):
			self.save_blob(blob_info) # store blob reference
			logging.info("Imported %s (content type: %s, size: %s)" %(blob_info.filename, blob_info.content_type, blob_info.size))
			csv_str = self.convertdata(blob_info, self.request.get('tgraphURI')) # convert from NTriples of CSV
			gsh = GSHelper()
			gsh.gs_init()
			target_filename = ".".join([blob_info.filename.rsplit(".")[0], GlobalUtility.DATA_POSTFIX])
			self.gsCopy(csv_str, target_filename, self.request.get('tgraphURI')) # copy CSV file to Google storage
			self.redirect('/datasets')
		else:
			logging.info("%s is already available here, not gonna upload it again ..." %blob_info.filename) 
			self.redirect('/datasets')

	# stores a reference to the uploaded blob
	def save_blob(self, blob_info):
		ntf = NTriplesFileModel()
		ntf.fname = blob_info.filename
		ntf.ntriplefile = blob_info.key()
		ntf.put()
	
	# converts the input RDF/NTriples to BigQuery's CSV format
	def convertdata(self, blob_info, graph_uri):
		logging.info("Converting with graph URI: %s" %graph_uri)
		ntfilecontent =  self.get_ntfile_contents(blob_info.key())
		#logging.info("NTriples (INPUT):")
		#logging.info(ntfilecontent)
		nt2csv = NTriple2CSV(None, None)
		csv_str = nt2csv.convertstr(ntfilecontent, graph_uri)
		#logging.info("CSV (OUTPUT):")
		#logging.info(csv_str)
		return csv_str
		
	def file_exists(self, fname):
		fileavailq = db.GqlQuery("SELECT * FROM NTriplesFileModel WHERE fname = :1", fname)
		if fileavailq.count(1) > 0:
			return True
		else:
			return False

	def get_ntfile_contents(self, blob_key):
		blob_reader = blobstore.BlobReader(blob_key, buffer_size=1048576) # set buffer to 1MB
		return blob_reader.read()
		
	def gsCopy(self, csv_str, fname, graph_uri):
		gs_target = "/".join([GlobalUtility.IMPORT_BUCKET, GlobalUtility.IMPORT_OBJECT, fname])
		uri = boto.storage_uri(gs_target, "gs")
		gskey = uri.new_key()
		gskey.set_contents_from_string(csv_str, None, True) # see http://boto.cloudhackers.com/ref/gs.html#boto.gs.key.Key.set_contents_from_filename
		gskey.set_acl('public-read')
		# this doesn't seem to work: gskey.set_metadata('graphURI', graphURI) ... hence a workaround:
		self.gsSetMetadata(fname, "graphURI=%s" %graph_uri)
		logging.info("Copied %s into graph %s in Google Storage" %(gs_target, graph_uri))
	
	def gsSetMetadata(self, fname, metadata):
		gs_target = "/".join([GlobalUtility.IMPORT_BUCKET, GlobalUtility.IMPORT_OBJECT, fname.split(".")[0]])
		gs_target = ".".join([gs_target, GlobalUtility.METADATA_POSTFIX])
		uri = boto.storage_uri(gs_target, "gs")
		gskey = uri.new_key()
		gskey.set_contents_from_string(metadata, None, True) # see http://boto.cloudhackers.com/ref/gs.html#boto.gs.key.Key.set_contents_from_filename


class AdminBQSEndpointHandler(webapp.RequestHandler):
	def get(self):
		user = users.get_current_user()
		if user:
			if users.is_current_user_admin():
				self.response.out.write("<div><a href=\"/\">Home</a> | <a href=\"/admin?cmd=listenv\">Environment</a> | <a href=\"/admin?cmd=remove_uploads\">Remove uploaded files</a> | <a href=\"/admin?cmd=reset_datasets\">Remove all datasets</a></div>")
				if self.request.get('cmd'):
					logging.info("Trying to execute admin command: %s" %self.request.get('cmd'))
					self.dispatchcmd(self.request.get('cmd'))
			else:
				self.response.out.write("Hi %s - you're not an admin, right? ;)" % user.nickname())

	def dispatchcmd(self, value):
		mname = 'exec_' + str(value)
		try:
			methodcall = getattr(self, mname)
			methodcall()
		except:
			self.response.out.write("<pre style='color:red'>Command unknown</pre>")
	
	def exec_remove_uploads(self):
		# remove all blobs
		allblobs = blobstore.BlobInfo.all();
		more = (allblobs.count() > 0)
		blobstore.delete(allblobs)
		# remove all references to blobs
		ntfiles = NTriplesFileModel.all()
		for ntfile in ntfiles:
		    ntfile.delete()
		self.response.out.write("<pre style='color:red'>Removed all uploaded files.</pre>")
	
	def exec_reset_datasets(self):
		# remove all objects from IMPORT_BUCKET
		gsh = GSHelper()
		gsh.gs_init()
		uri = boto.storage_uri(GlobalUtility.IMPORT_BUCKET, "gs")
		bucket = uri.get_bucket()
		for bobject in bucket:
			curkey = "/".join([GlobalUtility.IMPORT_BUCKET, bobject.name])
			try:
				gskey = boto.storage_uri(curkey, "gs")
				ometadata = gskey.delete_key()
				self.response.out.write("<p>Removed: %s</p>" %bobject.name)
			except:
				self.response.out.write("<p>Unable to remove: %s</p>" %bobject.name)
		self.response.out.write("<pre style='color:red'>Removed all datasets from Google Storage.</pre>")
	
	def exec_listenv(self):
		for name in os.environ.keys():
			self.response.out.write("%s = %s<br />\n" % (name, os.environ[name]))