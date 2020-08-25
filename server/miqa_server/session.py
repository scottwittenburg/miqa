import csv
import datetime
import io
import os
import re

from girder import logger
from girder.api.rest import Resource, setResponseHeader, setContentDisposition
from girder.api import access, rest
from girder.constants import AccessType
from girder.exceptions import RestException
from girder.api.describe import Description, autoDescribeRoute
from girder.models.collection import Collection
from girder.models.assetstore import Assetstore
from girder.models.folder import Folder
from girder.models.item import Item
from girder.models.setting import Setting
from girder.utility.progress import noProgress

from .setting import fileWritable, tryAddSites
from .constants import exportpathKey, importpathKey


class Session(Resource):
    def __init__(self):
        super(Session, self).__init__()
        self.resourceName = 'miqa'

        self.route('POST', ('csv', 'import',), self.csvImport)
        self.route('GET', ('sessions',), self.getSessions)
        self.route('GET', ('csv', 'export',), self.csvExport)
        self.route('GET', ('csv', 'export', 'download',), self.csvExportDownload)

    @access.user
    @autoDescribeRoute(
        Description('Retrieve all sessions in a tree structure')
        .errorResponse())
    def getSessions(self, params):
        return self._getSessions()

    def _getSessions(self):
        user = self.getCurrentUser()
        sessionsFolder = self.findSessionsFolder()
        if not sessionsFolder:
            return []
        experiments = []
        for experimentFolder in Folder().childFolders(sessionsFolder, 'folder', user=user):
            sessions = []
            experiments.append({
                'folderId': experimentFolder['_id'],
                'name': experimentFolder['name'],
                'sessions': sessions
            })
            for sessionFolder in Folder().childFolders(experimentFolder, 'folder', user=user):
                datasets = list(Item().find({'$query': {'folderId': sessionFolder['_id'],
                                                        'name': {'$regex': 'nii.gz$'}}, '$orderby': {'name': 1}}))
                sessions.append({
                    'folderId': sessionFolder['_id'],
                    'name': sessionFolder['name'],
                    'meta': sessionFolder.get('meta', {}),
                    'datasets': datasets
                })
        return experiments

    @access.user
    @autoDescribeRoute(
        Description('')
        .errorResponse())
    def csvImport(self, params):
        user = self.getCurrentUser()
        # logger.info('csvImport, user = {0}'.format(user))
        importpath = os.path.expanduser(Setting().get(importpathKey))
        if not os.path.isfile(importpath):
            raise RestException('import csv file doesn\'t exists', code=404)
        with open(importpath) as csv_file:
            existingSessionsFolder = self.findSessionsFolder(user)
            if existingSessionsFolder:
                existingSessionsFolder['name'] = 'sessions_' + \
                    datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
                Folder().save(existingSessionsFolder)
            sessionsFolder = self.findSessionsFolder(user, True)
            csv_content = csv_file.read()
            Item().createItem('csv', user, sessionsFolder, description=csv_content)
            reader = csv.DictReader(io.StringIO(csv_content))
            getField = findFieldHandler(reader.fieldnames)
            successCount = 0
            failedCount = 0
            sites = set()
            for row in reader:
                experimentId = getField('xnat_experiment_id', row)
                niftiPath = getField('nifti_folder', row)
                experimentNote = getField('experiment_note', row)
                site = getField('site', row)
                experimentId2 = getField('experiment_id_2', row)
                sites.add(site)
                scanId = getField('scan_id', row)
                scanType = getField('scan_type', row)
                relScanPath = getField('relative_scan_path', row)
                logger.info('read fields for {0}'.format(experimentId))
                niftiFolder = os.path.expanduser(os.path.join(niftiPath, relScanPath))
                if not os.path.isdir(niftiFolder):
                    logger.info('whoops, {0} is not a folder'.format(niftiFolder))
                    failedCount += 1
                    continue
                experimentFolder = Folder().createFolder(
                    sessionsFolder, experimentId, parentType='folder', reuseExisting=True)
                scanFolder = Folder().createFolder(
                    experimentFolder, relScanPath, parentType='folder', reuseExisting=True)
                meta = {
                    'experimentId': experimentId,
                    'experimentId2': experimentId2,
                    'experimentNote': experimentNote,
                    'site': site,
                    'scanId': scanId,
                    'scanType': scanType
                }
                # Merge note and rating if record exists
                if existingSessionsFolder:
                    existingMeta = self.tryGetExistingSessionMeta(
                        existingSessionsFolder, experimentId, relScanPath)
                    if(existingMeta and (existingMeta.get('note', None) or existingMeta.get('rating', None))):
                        meta['note'] = existingMeta.get('note', None)
                        meta['rating'] = existingMeta.get('rating', None)
                Folder().setMetadata(scanFolder, meta)
                currentAssetstore = Assetstore().getCurrent()
                Assetstore().importData(
                    currentAssetstore, parent=scanFolder, parentType='folder', params={
                        'fileIncludeRegex': '.+[.]nii[.]gz$',
                        'importPath': niftiFolder,
                    }, progress=noProgress, user=user, leafFoldersAsItems=False)
                successCount += 1
            print('just need to add sites and we will be done')
            tryAddSites(sites, self.getCurrentUser())
            return {
                "success": successCount,
                "failed": failedCount
            }

    @access.user
    @autoDescribeRoute(
        Description('')
        .errorResponse())
    def csvExport(self, params):
        exportpath = os.path.expanduser(Setting().get(exportpathKey))
        if not fileWritable(exportpath):
            raise RestException('export csv file is not writable', code=500)
        output = self.getExportCSV()
        with open(exportpath, 'w') as csv_file:
            csv_file.write(output.getvalue())

    @access.admin(cookie=True)
    @autoDescribeRoute(
        Description('')
        .errorResponse())
    def csvExportDownload(self, params):
        setResponseHeader('Content-Type', 'text/csv')
        setContentDisposition('_output.csv')
        output = self.getExportCSV()
        return lambda: [(yield x) for x in output.getvalue()]

    def getExportCSV(self):
        def convertRatingToDecision(rating):
            return {
                None: 0,
                'questionable': 0,
                'good': 1,
                'usableExtra': 2,
                'bad': -1
            }[rating]
        sessionsFolder = self.findSessionsFolder()
        items = list(Folder().childItems(sessionsFolder, filters={'name': 'csv'}))
        if not len(items):
            raise RestException('doesn\'t contain a csv item', code=404)
        csvItem = items[0]
        reader = csv.DictReader(io.StringIO(csvItem['description']))
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            experience = Folder().findOne({
                'name': row['xnat_experiment_id'],
                'parentId': sessionsFolder['_id']
            })
            if not experience:
                continue
            session = Folder().findOne({
                'name': row['scan_id']+'_'+row['scan_type'],
                'parentId': experience['_id']
            })
            if not session:
                continue
            row['decision'] = convertRatingToDecision(session.get('meta', {}).get('rating', None))
            row['scan_note'] = session.get('meta', {}).get('note', None)
            writer.writerow(row)
        return output

    def findSessionsFolder(self, user=None, create=False):
        collection = Collection().findOne({'name': 'miqa'})
        sessionsFolder = Folder().findOne({'name': 'sessions', 'baseParentId': collection['_id']})
        if not create:
            return sessionsFolder
        else:
            if not sessionsFolder:
                return Folder().createFolder(collection, 'sessions',
                                             parentType='collection', creator=user)

    def tryGetExistingSessionMeta(self, sessionsFolder, experimentId, scan):
        experimentFolder = Folder().findOne(
            {'name': experimentId, 'parentId': sessionsFolder['_id']})
        if not experimentFolder:
            return None
        sessionFolder = Folder().findOne(
            {'name': scan, 'parentId': experimentFolder['_id']})
        if not sessionFolder:
            return None
        return sessionFolder.get('meta', {})


def finderForXNATArchiveData(fieldName, row):
    if fieldName == 'relative_scan_path':
        return '{0}_{1}'.format(row['scan_id'], row['scan_type'])
    elif fieldName == 'site' or fieldName == 'experiment_id_2':
        niftiPath = row['nifti_folder']
        m = re.search(r".+/([^_]+)_incoming/[^/]+/(.+)-\d{8}/RESOURCES", niftiPath)
        if m:
            return m.group(1) if fieldName == 'site' else m.group(2)
    return row[fieldName]


def finderForSampleBidsData(fieldName, row):
    if fieldName == 'xnat_experiment_id':
        return row['experiment_id']
    elif fieldName == 'relative_scan_path':
        return row['filename']
    elif fieldName == 'experiment_id_2':
        return 'N/A'
    return row[fieldName]


def defaultFinder(fieldName, row):
    if fieldName == 'relative_scan_path':
        return '{0}_{1}'.format(row['scan_id'], row['scan_type'])
    return row[fieldName]


def findFieldHandler(fieldnames):
    if 'MQy:VRX' in fieldnames and 'MQy:VRY' in fieldnames and 'MQy:VRZ' in fieldnames:
        return finderForSampleBidsData
    elif 'site' not in fieldnames and 'experiment_id_2' not in fieldnames:
        return finderForXNATArchiveData
    return defaultFinder
