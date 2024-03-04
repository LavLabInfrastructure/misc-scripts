from omero.gateway import BlitzGateway, ImageWrapper
from collections import Counter
import re
conn = BlitzGateway('','', host= 'wss://wsi.lavlab.mcw.edu/omero-wss', secure= True)
conn.connect()
conn.SERVICE_OPTS.setOmeroGroup(-1)

#Dupe finder
#Used to remove dupes before renaming 
name_list = []
for x in conn.getObjects('image'):
    name_list.append(x.getName())
element_count = Counter(name_list)
duplicates = [element for element, count in element_count.items() if count > 1]
print("Duplicates in the list are:", duplicates)