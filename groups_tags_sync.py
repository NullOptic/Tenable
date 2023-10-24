# This script will sync agent groups to asset tags. It will create a tag category "Agent Groups" if it does not exist, and then create tags in that category for every group you have.
# This is a workaround for Tenable currently lacking functionality between tags and groups https://suggestions.tenable.com/ideas/IOVM-I-995
# This script was built for Python 3.10 and can run as a scheduled task. Add your API keys to line 34

import logging
import time
import sys
import os
import pickle
import pprint
from tenable.io import TenableIO
from datetime import datetime


#log output to a file
logging.basicConfig(level=logging.INFO,
                    filename='groups_tag_sync.log',
                    format='%(asctime)s - %(levelname)s - %(message)s')
#log output to console
root = logging.getLogger()
root.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)


pp = pprint.PrettyPrinter(indent=2)
non_bmp_map = dict.fromkeys(range(0x10000, sys.maxunicode + 1), 0xfffd)


# https://github.com/tenable/pyTenable/issues/681
tio = TenableIO(access_key="", secret_key="") #api_readwrite
tio_tag_data = 'tio_tags_cache.pickle'
tio_asset_data = 'tio_asset_cache.pickle'
tio_assets = {}
tio_data = 'tio_agent_cache.pickle'
tio_agents = {}
tag_name_uuid = {}
tag_uuid_name = {}
tag_tree = {}
agent_groups = {}

logging.info('Starting script')

#for tag in tio.tags.list():
for category in tio.tags.list_categories():
    tag_tree.update({category['name']: {}})

if "Agent Groups" not in tag_tree:
    logging.info(f"Agent Groups category not found, creating...")
    tio.tags.create_category('Agent Groups', description="Tags synced via script with Agent Groups")

#print('Categories:')
for category in tio.tags.list_categories():
    #print(category['name'])
    tag_name_uuid.update({category['name']: category['uuid']})
    tag_uuid_name.update({category['uuid']: category['name']})
    tag_tree.update({category['name']: {}})
    for tag in tio.tags.list(('category_name', 'eq', category['name'])):
        tag_tree[category['name']].update({tag['value']: {}})
        tag_name_uuid.update({tag['value']: tag['uuid']})
        tag_uuid_name.update({tag['uuid']: tag['value']})



print('done')
print('tag tree:')
pp.pprint(tag_tree)
print('tag_name_uuid:')
pp.pprint(tag_name_uuid)
print('tag_uuid_name:')
pp.pprint(tag_uuid_name)

print()
print()




# Get latest agent data
#if False: # Use this to update every time
if os.path.isfile(tio_asset_data) and (datetime.now().date() == datetime.fromtimestamp(os.path.getmtime(tio_asset_data)).date()):
    logging.info('Tenable asset data is already updated, loading from file')
    pickle_in = open(tio_asset_data, 'rb')
    tio_assets = pickle.load(pickle_in)
else:
    logging.info("Refreshing Tenable.io data because it was not updated today or cache is disabled")
    try:
        logging.info('Downloading asset data from Tenable.io')
        co = 0
        for item in tio.assets.list():
            tio_assets.update({item['id']: item})
            print(len(tio_assets))
            co += 1
        with open(tio_asset_data, 'wb') as td:
            pickle.dump(tio_assets, td)
    except Exception as e:
        logging.error(f'Trouble requesting Tenable data: {e}')
    logging.info('Tenable.io query complete')
logging.info('Asset data loaded')


# Get latest agent data
#if False: # Use this to update every time
if os.path.isfile(tio_data) and (datetime.now().date() == datetime.fromtimestamp(os.path.getmtime(tio_data)).date()):
    logging.info('Tenable agent data is already updated, loading from file')
    pickle_in = open(tio_data, 'rb')
    tio_agents = pickle.load(pickle_in)
else:
    logging.info("Refreshing Tenable.io data because it was not updated today or cache is disabled")
    try:
        logging.info('Downloading Agent data from Tenable.io')
        co = 0
        for item in tio.agents.list():
            #pp.pprint(item)
            tio_agents.update({item['uuid']: item})
            print(len(tio_agents))
            co += 1
        with open(tio_data, 'wb') as td:
            pickle.dump(tio_agents, td)
    except Exception as e:
        logging.error(f'Trouble requesting Tenable data: {e}')
    logging.info('Tenable.io query complete')
logging.info('Agent data loaded')

# Create the agent_groups dict: {agent_name: [groups]}
for agent in tio_agents:
    t_set = set()
    a = tio_agents[agent]
    #print(a['name'])
    #pp.pprint(a)
    if 'groups' in a:
        for g in a['groups']:
            #print(g)
            t_set.add(g['name'])
            if g['name'] not in tag_name_uuid:
                logging.warning(f"Tag for {g['name']} does not exist, creating...")
                creation_result = tio.tags.create('Agent Groups', g['name'])
                #print(creation_result)
                tag_name_uuid.update({g['name']: creation_result['uuid']})
                logging.info(f"Created tag")
                time.sleep(1)
        agent_groups.update({a['name'].upper(): t_set})
    else:
        #print(f'No groups found in {a}')
        pass

# Pull down Agent Group tags again in case any were created
for tag in tio.tags.list(('category_name', 'eq', 'Agent Groups')):
    tag_tree['Agent Groups'].update({tag['value']: {}})
    tag_name_uuid.update({tag['value']: tag['uuid']})
    tag_uuid_name.update({tag['uuid']: tag['value']})

t = len(tio_assets)
c = 0
for ast in tio_assets:
    c += 1
    t_tags = {}
    tag_set = set()
    remove_uuids = []
    add_uuids = []
    asset = tio_assets[ast]
    #print(ast)
    logging.info(f"[{c}/{t}] {asset.get('hostname', 'HostnameNotFound')}")
    t_tags = tio.assets.tags(ast) # Get current tags for this asset
    #pp.pprint(t_tags)
    for tag in t_tags['tags']:  # Get only tags in the Agent Groups category
        if tag['category_name'] == 'Agent Groups':
            #print(tag['value'])
            tag_set.add(tag['value'])
    if len(asset['hostname']) == 0:  # Skip if no hostname
        continue
    if asset['hostname'][0].upper() not in agent_groups:
        groups_set = set()
    else:
        groups_set = agent_groups[asset['hostname'][0].upper()]
    if tag_set == groups_set:  # Match, nothing to do so skip
        continue
    print(f"[{asset['hostname'][0].upper()}][{c}/{t}] tag_set: {tag_set} === groups_set: {groups_set}")
    remove_tags = tag_set.difference(groups_set)
    add_tags = groups_set.difference(tag_set)
    print(f"[{asset['hostname'][0].upper()}][{c}/{t}] add_tags: {add_tags} === remove_tags: {remove_tags}")


    if len(remove_tags) > 0:
        #time.sleep(1)
        logging.info(f"[{asset['hostname'][0].upper()}][{c}/{t}] Removing tags: {remove_tags} ")
        try:
            for r in remove_tags:
                remove_uuids.append(tag_name_uuid[r])
            #logging.info(f"[{asset['hostname'][0].upper()}][{c}/{t}] Tag UUIDs: {remove_uuids} ")
            tio.assets.assign_tags('remove', [ast], remove_uuids)
            logging.info(f"[{asset['hostname'][0].upper()}][{c}/{t}] Removed tags")
        except Exception as e:
            logging.error(f"Problem removing tags because: {e}")
    if len(add_tags) > 0:
        #time.sleep(1)
        logging.info(f"[{asset['hostname'][0].upper()}] Adding tags: {add_tags} ")
        try:
            for a in add_tags:
                add_uuids.append(tag_name_uuid[a])
            logging.info(f"[{asset['hostname'][0].upper()}] Tag UUIDs: {add_uuids} ")
            tio.assets.assign_tags('add', [ast], add_uuids)
            logging.info(f"[{asset['hostname'][0].upper()}] Added tags")
        except Exception as e:
            logging.error(f"Problem adding tags because: {e}")

    print()

logging.info('done')
# https://pytenable.readthedocs.io/en/stable/api/io/tags.html
