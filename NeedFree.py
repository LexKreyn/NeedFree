from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED
import traceback
import requests
import datetime
import queue
import time
import json
import pytz
import bs4
import re


API_URL_TEMPLATE = "https://store.steampowered.com/search/results/?query&start={pos}&count=100&hidef2p=1&infinite=1&ndl=1"
THREAD_CNT = 8

free_list = queue.Queue()


def fetch_Steam_json_response(url):
    ''' Fetch json response from Steam API
    URL:            Steam WebAPI url

    return:         json content
    '''
    while True:
        try:
            with requests.get(url, timeout = 5) as response:
                ret_json = response.json()
            return ret_json
        except Exception as e:
            print(e)
            time.sleep(10)
            continue

def get_free_goods(start, append_list = False):
    ''' Extract discount goods list in a list of 100 products
    start:          start page index
    append_list:    if to append new found free goods to final list

    return:         goods_count
    '''

    global free_list
    retry_time = 3

    while retry_time >= 0:
        response_json = fetch_Steam_json_response(API_URL_TEMPLATE.format(pos = start))
        try:
            goods_count = response_json["total_count"]
            goods_html = response_json["results_html"]
            page_parser = bs4.BeautifulSoup(goods_html, "html.parser")
            full_discounts_div = page_parser.find_all(name = "div", attrs = {"class":"search_discount_block"})
            sub_free_list = [
                {
                    'id': None,
                    'popularity': start + idx,
                    'discount': div.parent.parent.parent.parent.find(name="div", attrs={"class": "search_discount_block"}).get("data-discount"),
                    'price': div.parent.parent.parent.parent.find(name="div", attrs={"class": "discount_original_price"}),
                    'price_final': div.parent.parent.parent.parent.find(name="div", attrs={"class": "discount_final_price"}).get_text(),
                    'title': div.parent.parent.parent.parent.find(name="span", attrs={"class": "title"}).get_text(),
                    'link': div.parent.parent.parent.parent.get("href"),
                    'image': div.parent.parent.parent.parent.find_all("div")[0].find("img").get("src"),
                    'tags': div.parent.parent.parent.parent.get("data-ds-tagids"),
                    'is_bundle': div.parent.parent.parent.parent.get("data-ds-bundleid"),
                    'bundle_data': div.parent.parent.parent.parent.get("data-ds-bundle-data"),
                    'is_soundtrack': div.parent.parent.parent.parent.find(name="span", attrs={"class": "music"}),
                    'for_win': div.parent.parent.parent.parent.find(name="span", attrs={"class": "win"}),
                    'for_mac': div.parent.parent.parent.parent.find(name="span", attrs={"class": "mac"}),
                    'for_linux': div.parent.parent.parent.parent.find(name="span", attrs={"class": "linux"}),
                    'vr_support': div.parent.parent.parent.parent.find(name="span", attrs={"class": "vr_supported"}),
                    'release': div.parent.parent.parent.parent.find(name="div", attrs={"class": "search_released"}),
                    'reviews': div.parent.parent.parent.parent.find(name="span", attrs={"class": "search_review_summary"})
                } for idx, div in enumerate(full_discounts_div)
            ]

            counter = 0
            if append_list:
                for sub_free in sub_free_list:
                    if not sub_free['discount']:
                        sub_free['discount'] = '0'

                    if sub_free['price']:
                        sub_free['price'] = sub_free['price'].get_text()
                    else:
                        sub_free['price'] = ''

                    if sub_free['price_final'] == 'Free':
                        sub_free['price_final'] = '0'

                    if not sub_free['price']:
                        sub_free['price'] = sub_free['price_final']

                    if sub_free['release']:
                        sub_free['release'] = sub_free['release'].get_text()
                    else:
                        sub_free['release'] = ''

                    if sub_free['reviews']:
                        sub_free['reviews'] = sub_free['reviews'].get("data-tooltip-html")
                    else:
                        sub_free['reviews'] = r'None<br>0% of the 0'

                    counter += 1
                    free_list.put(sub_free)

            return goods_count
        except Exception as e:
            print("get_free_goods: error on start = %d, remain retry %d time(s)" % (start, retry_time))
            print(e)
            print(traceback.format_exc())
            retry_time -= 1
    print("get_free_goods: error on start = %d, throw" % (start))

    return 0

# Get total count of free goods
tryget_first_page = get_free_goods(0)
total_count = tryget_first_page

# Multi-thread crawling
threads = ThreadPoolExecutor(max_workers = THREAD_CNT)
futures = [threads.submit(get_free_goods, index, True) for index in range(0, total_count, 100)]

wait(futures, return_when=ALL_COMPLETED)

# Process free list
final_free_list = list()
free_ids = set()
while not free_list.empty():
    free_item = free_list.get()

    game_id = re.search(r'.com\/[a-z]+\/(\d+)\/', free_item['link'])
    if game_id is None:
        continue

    game_id = int(game_id.group(1))
    if game_id in free_ids:
        continue

    free_item['id'] = game_id

    free_item['tags'] = json.loads(free_item['tags'] or '[]')
    free_item['bundle_data'] = json.loads(free_item['bundle_data'] or r'{}')

    free_item['discount'] = int(free_item['discount'])

    free_item['is_bundle'] = bool(free_item['is_bundle'])
    free_item['is_soundtrack'] = bool(free_item['is_soundtrack'])
    free_item['for_win'] = bool(free_item['for_win'])
    free_item['for_mac'] = bool(free_item['for_mac'])
    free_item['for_linux'] = bool(free_item['for_linux'])
    free_item['vr_support'] = bool(free_item['vr_support'])

    free_item['release'] = free_item['release'].strip() or ''

    score, percent, users = re.search(r'^([a-zA-Z ]+)\<br\>(\d{1,3})% of the ([\d,]+)', free_item['reviews']).groups()
    free_item['review_score'] = score
    free_item['review_percent'] = int(percent)
    free_item['review_users'] = int(users.replace(',' ,''))

    free_ids.add(game_id)
    final_free_list.append(free_item)

today = datetime.datetime.now(tz=pytz.timezone("Europe/Moscow"))
final_free_list_part1 = final_free_list[:len(final_free_list)]
final_free_list_part2 = final_free_list[len(final_free_list):]

with open("free_goods_detail_part1.json", "w", encoding="utf-8") as fp:
    json.dump({
        "total_count": len(final_free_list_part1),
        "free_list": final_free_list_part1,
        "update_time": today.strftime('%Y-%m-%d %H:%M:%S')
    }, fp)

with open("free_goods_detail_part2.json", "w", encoding="utf-8") as fp:
    json.dump({
        "total_count": len(final_free_list_part2),
        "free_list": final_free_list_part2,
        "update_time": today.strftime('%Y-%m-%d %H:%M:%S')
    }, fp)
