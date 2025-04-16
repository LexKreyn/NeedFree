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


API_URL_TEMPLATE = "https://store.steampowered.com/search/results/?query&start={pos}&count=100&specials=1&infinite=1"
THREAD_CNT = 8

free_list = queue.Queue()


def fetch_Steam_json_response(url):
    while True:
        try:
            with requests.get(url, timeout = 5) as response:
                ret_json = response.json()
            return ret_json
        except Exception as e:
            print('\n'.join(traceback.format_exception(e)))
            time.sleep(10)
            continue


def fetch_cart_id(url):
    while True:
        try:
            with requests.get(url, timeout = 5) as response:
                cart_id = re.search(r'addToCart\((\d+)\);', response.text)
                if cart_id is not None:
                    cart_id = int(cart_id.group(1))
                else:
                    raise ValueError('no cart id found: {}'.format(url))
            return cart_id
        except Exception as e:
            print('\n'.join(traceback.format_exception(e)))
            time.sleep(10)
            continue


def fetch_game_details(cart_id, region):
    while True:
        try:
            with requests.get('https://store.steampowered.com/api/packagedetails/?cc={}&packageids={}'.format(region, cart_id), timeout = 5) as response:
                ret_json = response.json()
            return ret_json[str(cart_id)]
        except Exception as e:
            print('\n'.join(traceback.format_exception(e)))
            time.sleep(10)
            continue


def fetch_game_details_us(cart_id):
    return fetch_game_details(cart_id, 'us')


def fetch_game_details_gb(cart_id):
    return fetch_game_details(cart_id, 'gb')


def fetch_game_details_fr(cart_id):
    return fetch_game_details(cart_id, 'fr')


def fetch_game_details_jp(cart_id):
    return fetch_game_details(cart_id, 'jp')


def fetch_game_details_ru(cart_id):
    return fetch_game_details(cart_id, 'ru')


def fetch_game_details_br(cart_id):
    return fetch_game_details(cart_id, 'br')


def get_free_goods(start, append_list = False):
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
                    # div.parent.parent.parent.parent.find(name="div", attrs={"class": "discount_original_price"}),
                    # div.parent.parent.parent.parent.find(name="div", attrs={"class": "discount_final_price"}).get_text(),
                    div.parent.parent.parent.parent.find(name="span", attrs={"class": "title"}).get_text(),
                    div.parent.parent.parent.parent.get("href"),
                    div.parent.parent.parent.parent.find_all("div")[0].find("img").get("src")
                ] for div in full_discounts_div
            ][:3]

            if append_list:
                for sub_free in sub_free_list:
                    if sub_free[0] and sub_free[0] != '0':
                        sub_free[0] = int(sub_free[0])
                        game_id = re.search(r'.com\/[a-z]+\/(\d+)\/', sub_free[2]).group(1)
                        cart_id = fetch_cart_id(sub_free[2])

                        details_us = fetch_game_details_us(cart_id)
                        details_gb = fetch_game_details_gb(cart_id)
                        details_fr = fetch_game_details_fr(cart_id)
                        details_jp = fetch_game_details_jp(cart_id)
                        details_ru = fetch_game_details_ru(cart_id)
                        details_br = fetch_game_details_br(cart_id)
                        prices = {
                            'us': {
                                'currency': details_us['data']['price']['currency'],
                                'initial': details_us['data']['price']['initial'] / 100,
                                'final': details_us['data']['price']['final'] / 100,
                            },
                            'gb': {
                                'currency': details_gb['data']['price']['currency'],
                                'initial': details_gb['data']['price']['initial'] / 100,
                                'final': details_gb['data']['price']['final'] / 100,
                            },
                            'fr': {
                                'currency': details_fr['data']['price']['currency'],
                                'initial': details_fr['data']['price']['initial'] / 100,
                                'final': details_fr['data']['price']['final'] / 100,
                            },
                            'jp': {
                                'currency': details_jp['data']['price']['currency'],
                                'initial': details_jp['data']['price']['initial'] / 100,
                                'final': details_jp['data']['price']['final'] / 100,
                            },
                            'ru': {
                                'currency': details_ru['data']['price']['currency'],
                                'initial': details_ru['data']['price']['initial'] / 100,
                                'final': details_ru['data']['price']['final'] / 100,
                            },
                            'br': {
                                'currency': details_br['data']['price']['currency'],
                                'initial': details_br['data']['price']['initial'] / 100,
                                'final': details_br['data']['price']['final'] / 100,
                            }
                        }
                        sub_free = [int(game_id), cart_id, sub_free[0], prices] + sub_free[1:]
                        free_list.put(sub_free)

            return goods_count
        except Exception as e:
            print("get_free_goods: error on start = %d, remain retry %d time(s)" % (start, retry_time))
            print('\n'.join(traceback.format_exception(e)))
            retry_time -= 1
    print("get_free_goods: error on start = %d, throw" % (start))

    return 0

# Get total count of free goods
tryget_first_page = get_free_goods(0)
total_count = tryget_first_page
total_count = 3

# Multi-thread crawling
threads = ThreadPoolExecutor(max_workers = THREAD_CNT)
futures = [threads.submit(get_free_goods, index, True) for index in range(0, total_count, 100)]

wait(futures, return_when=ALL_COMPLETED)

# Process free list
final_free_list = []
free_ids = set()
while not free_list.empty():
    free_item = free_list.get()

    if free_item[0] in free_ids:
        continue

    free_ids.add(free_item[0])
    final_free_list.append(free_item)

final_free_list = sorted_data = sorted(final_free_list, key=lambda x: (-x[2], x[4]))

with open("free_goods_detail.json", "w", encoding="utf-8") as fp:
    json.dump({
        "total_count": len(final_free_list),
        "free_list": final_free_list,
        "update_time": datetime.datetime.now(tz=pytz.timezone("Europe/Moscow")).strftime('%Y-%m-%d %H:%M:%S')
    }, fp)
