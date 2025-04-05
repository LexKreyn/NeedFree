from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED
import requests
import datetime
import queue
import time
import json
import pytz
import bs4


API_URL_TEMPLATE = "https://store.steampowered.com/search/results/?query&start={pos}&count=100&infinite=1"
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
                [
                    div.parent.parent.parent.parent.find(name="div", attrs={"class": "search_discount_block"}).get('data-discount'),
                    div.parent.parent.parent.parent.find(name="div", attrs={"class": "discount_original_price"}),
                    div.parent.parent.parent.parent.find(name="div", attrs={"class": "discount_final_price"}).get_text(),
                    div.parent.parent.parent.parent.find(name="span", attrs={"class": "title"}).get_text(),
                    div.parent.parent.parent.parent.get("href"),
                    div.parent.parent.parent.parent.find_all("div")[0].find("img").get("src")
                ] for div in full_discounts_div
            ]

            if append_list:
                for sub_free in sub_free_list:
                    if sub_free[0] and sub_free[0] != '0':
                        if sub_free[1]:
                            sub_free[1] = sub_free[1].get_text()
                        sub_free[0] = int(sub_free[0])
                        print(sub_free)
                        free_list.put(sub_free)

            return goods_count
        except Exception as e:
            print("get_free_goods: error on start = %d, remain retry %d time(s)" % (start, retry_time))
            print(e)
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
final_free_list = []
free_names = set()
while not free_list.empty():
    free_item = free_list.get()
    game_name = free_item[0]
    if game_name not in free_names:
        free_names.add(game_name)
        final_free_list.append(free_item)

final_free_list = sorted_data = sorted(final_free_list, key=lambda x: (-x[0], x[1]))

with open("free_goods_detail.json", "w", encoding="utf-8") as fp:
    json.dump({
        "total_count": len(final_free_list),
        "free_list": final_free_list,
        "update_time": datetime.datetime.now(tz=pytz.timezone("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S')
    }, fp)
