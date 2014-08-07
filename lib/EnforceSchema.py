import collections
import settings
import datetime

class Enforcer:
  '''
  translates schema from ADSRecords to alternative schema
  '''
  def __init__(self):
    self.dispatcher = {
      'general': self._generalEnforcer,
      'properties':self._propertiesEnforcer,
      'references':self._referencesEnforcer,
      'relations':self._relationsEnforcer,
    }

  def ensureLanguageSchema(self,item):
    if isinstance(item,basestring):
      L = [{
        'lang':'en',
        'text': item
      }]
    else:
      L = self.ensureList(item)
      for i in L:
        if '@lang' not in i:
          i['lang'] = 'en'
        if '#text' in i:
          i['text'] = i['#text']
          del i['#text']
    return L

  def ensureList(self,item):
    if item is None:
      return []
    return item if isinstance(item,list) else [item]

  def parseBool(self,item):
    return False if item in ['false','False',False,'FALSE','f',0,'0'] else True

  def finalPassEnforceSchema(self,record):
    '''
    Responsible for final cleanup of data before writing to mongo
    . Removes 'tempdata'
    . De-duplicates
    . Attempts to coerce types
    '''
    blocklevel_removals = ['tempdata']
    toplevel_removals = ['@bibcode']

    for i in toplevel_removals:
      if i in record:
        del record[i]

    for key,block in record['metadata'].iteritems():
      for i in blocklevel_removals:
        if i in block:
          del block[i]
    #De-duplicate
    #Coerce to correct type
    return record


  def enforceTopLevelSchema(self,record,JSON_fingerprint):
    r = record
    r['JSON_fingerprint'] = JSON_fingerprint
    r['bibcode'] = record['@bibcode']
    r['modtime'] = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    #explicitly skip 'text', 'metadata'
    return r

  def enforceMetadataSchema(self,blocks):
    results = []
    for block in self.ensureList(blocks):
      b = self.dispatcher[block['@type']](block)
      results.append(b)
    return results

  def _generalEnforcer(self,block):
    #Shorthands
    g = block.get
    eL = self.ensureList
    eLS = self.ensureLanguageSchema

    r = {}

    #tempdata necessary for some merger rules; will be deleted before commiting to mongo
    r['tempdata'] = {
      'primary':            self.parseBool(g('@primary',True)) ,
      'alternate_journal':  self.parseBool(g('@alternate_journal',False)),
      'type':               g('@type'),
      'origin':             g('@origin'),
      'bibcode':            g('bibcode'),
      'modtime':            g('modification_time'),
    }

    r['arxivcategories'] = eL(g('arxivcategories',[]))
    
    r['keywords'] = []
    for i in eL(g('keywords',[])):
      for j in eL(i.get('keyword',[])):
        r['keywords'].append({
          'origin':     g('@origin'),
          'type':       i.get('@type'),
          'channel':    j.get('@channel'),
          'original':   j.get('original'),
          'normalized': j.get('normalized'),
          })
    
    r['titles'] = []
    for i in eLS(g('title',[])):
      r['titles'].append(i)

    r['abstracts'] = []
    for i in eLS(g('abstract',[])):
      i['origin'] = g('@origin')
      r['abstracts'].append(i)

    r['authors'] = []
    for i in eL(g('author',[])):
      orcid = eL(i.get('author_ids',[]))
      assert len(orcid)==1 or len(orcid)==0
      orcid = orcid[0]['author_id'].replace('ORCID:','') if orcid else None
      r['authors'].append({
        'number': i.get('@nr'),
        'type': i.get('type'),
        'affiliations': [j.get('affiliation') for j in eL(i.get('affiliations',[]))],
        'emails': [j['email'] for j in eL(i.get('emails',[]))],
        'orcid': orcid,
        'name': {
          'native':     i['name'].get('native'),
          'western':    i['name'].get('western'),
          'normalized': i['name'].get('normalized'),
        },
      })

    r['publication'] = {}
    r['publication']['origin'] =        g('@origin')
    r['publication']['volume'] =        g('volume')
    r['publication']['issue'] =         g('issue')
    r['publication']['page'] =          g('page')
    r['publication']['page_last'] =     g('lastpage')
    r['publication']['page_range'] =    g('page_range')
    r['publication']['page_count'] =    g('pagenumber')
    r['publication']['electronic_id'] = g('electronic_id')
    r['publication']['name'] = {
      'raw':        g('journal'),
      'canonical':  g('canonical_journal'),
    }

    r['publication']['dates'] = []
    for i in eL(g('dates',[])):
      r['publication']['dates'].append({
        'type':     i['date'].get('@type'),
        'content':  i['date'].get('#text'),
      })
    if 'publication_year' in block:
      r['publication']['dates'].append({
        'type': 'publication_year',
        'content':  g('publication_year'),
      })


    r['conf_metadata'] = {
      'origin': g('@origin'),
      'content': g('conf_metadata')
    }

    keys = ['pubnote','comment','copyright','isbns','issns','DOI']
    for k in keys:
      r[k.lower()] = [{'origin': g('@origin'), 'content': i} for i in eL(g(k,[]))]
    
    return r


  def _propertiesEnforcer(self,block):
    r = {}
    g = block.get
    eL = self.ensureList

    #tempdata necessary for some merger rules; will be deleted before commiting to mongo
    r['tempdata'] = {
      'primary':            self.parseBool(g('@primary',True)) ,
      'alternate_journal':  self.parseBool(g('@alternate_journal',False)),
      'type':               g('@type'),
      'origin':             g('@origin'),
      'modtime':            g('modification_time'),
    }

    r['associates'] = []
    for i in eL(g('associates',[])):
      for j in eL(i.get('associate',[])):
        r['associates'].append({
          'origin': g('@origin'),
          'comment': j.get('@comment'),
          'content': j.get('#text'),
        })

    r['pubtype'] = {
      'origin':   g('@origin'),
      'content':  g('pubtype'),
    }

    r['databases'] = []
    for i in eL(g('databases',[])):
      r['databases'].append({
        'origin': g('@origin'),
        'conent': i.get('database'),
      })

    for k in ['openaccess','nonarticle','ocrabstract','private','refereed']:
      r[k] = self.parseBool(g(k,False))

    return r



  def _referencesEnforcer(self,block):
    r = {}
    g = block.get
    eL = self.ensureList

    r['tempdata'] = {
      'primary':            self.parseBool(g('@primary',True)) ,
      'alternate_journal':  self.parseBool(g('@alternate_journal',False)),
      'type':               g('@type'),
      'modtime':            g('modification_time'),
      'origin':             g('@origin'),
    }

    r['references'] = []
    for i in eL(g('reference',[])):
      r['references'].append({
        'origin':     g('@origin'),
        'bibcode':    i.get('@bibcode'),
        'doi':        i.get('@doi'),
        'score':      i.get('@score'),
        'extension':  i.get('@extension'),
        'arxid':      i.get('@arxiv'),
        'content':    i.get('#text'),
        })
    return r

  def _relationsEnforcer(self,block):
    r = {}
    g = block.get
    eL = self.ensureList

    r['tempdata'] = {
      'primary':            self.parseBool(g('@primary',True)) ,
      'alternate_journal':  self.parseBool(g('@alternate_journal',False)),
      'type':               g('@type'),
      'modtime':            g('modification_time'),
      'origin':             g('@origin'),
    }

    r['preprints'] = []
    for i in eL(g('preprintid',[])):
      r['preprints'].append({
        'origin':   g('origin'),
        'ecode':    i.get('@ecode'),
        'content':  i.get('#text'),
      })

    r['alternates'] = []
    for i in eL(g('alternates',[])):
      for j in eL(i.get('alternate',[])):
        r['alternates'].append({
          'origin':   g('origin'),
          'type':     j.get('@type'),
          'content':  j.get('#text'),
        })

    r['links'] = []
    for i in eL(g('links',[])):
      for j in eL(i.get('link',[])):
        if j.get('@type')=='ADSlink': continue
        r['links'].append({
          'origin':   g('origin'),
          'type':     j.get('@type'),
          'url':      j.get('@url'),
          'title':    j.get('@title'),
          'count':    j.get('@count'),
        })
    return r