from flask import Flask, request
import math, json, time, requests
from google import genai
import os

# 載入 LINE Message API 相關函式庫
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, StickerSendMessage, ImageSendMessage, LocationSendMessage
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, MessagingApiBlob

app = Flask(__name__)

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')
CWA_WEATHER_API = os.getenv('CWA_WEATHER_API')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MOENV_API_KEY = os.getenv('MOENV_API_KEY')

def earthquake_information():  # 地震資訊
    result = []
    # code = os.getenv('CWA_WEATHER_API')
    try:
        # 小區域 
        url = f'https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0016-001?Authorization={CWA_WEATHER_API}'
        req1 = requests.get(url)  
        data1 = req1.json()       
        eq1 = data1['records']['Earthquake'][0]     # 取得第一筆地震資訊
        t1 = data1['records']['Earthquake'][0]['EarthquakeInfo']['OriginTime']

        # 顯著有感 
        url2 = f'https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={CWA_WEATHER_API}'
        req2 = requests.get(url2)  
        data2 = req2.json()      
        eq2 = data2['records']['Earthquake'][0]     # 取得第一筆地震資訊
        t2 = data2['records']['Earthquake'][0]['EarthquakeInfo']['OriginTime']
        
        result = [eq1['ReportContent'], eq1['ReportImageURI']]      # 先使用小區域地震
        if t2>t1:
          result = [eq2['ReportContent'], eq2['ReportImageURI']]    # 如果顯著有感地震時間較近，就用顯著有感地震
    except Exception as e:
        print(e)
        result = ['抓取失敗...','']
    return result

def forecast(address):  # 氣象局天氣預報
    """
    根據地址查詢天氣預報
    參數:
        address: 完整地址，例如 '新北市永和區00路xx號'
    返回:
        dict: 包含該地區天氣資訊的字典
    """
    # 縣市的代碼
    api_list = {
        "宜蘭縣":"F-D0047-001", "桃園市":"F-D0047-005", "新竹縣":"F-D0047-009", "苗栗縣":"F-D0047-013",
        "彰化縣":"F-D0047-017", "南投縣":"F-D0047-021", "雲林縣":"F-D0047-025", "嘉義縣":"F-D0047-029",
        "屏東縣":"F-D0047-033", "臺東縣":"F-D0047-037", "花蓮縣":"F-D0047-041", "澎湖縣":"F-D0047-045",
        "基隆市":"F-D0047-049", "新竹市":"F-D0047-053", "嘉義市":"F-D0047-057", "臺北市":"F-D0047-061",
        "高雄市":"F-D0047-065", "新北市":"F-D0047-069", "臺中市":"F-D0047-073", "臺南市":"F-D0047-077",
        "連江縣":"F-D0047-081", "金門縣":"F-D0047-085"
    }
    
    # 根據地址，取得縣市代碼
    city_id = None
    city_name = None
    for name in api_list:
        if name in address:
            city_id = api_list[name]
            city_name = name
            break
    
    if not city_id:
        print("找不到對應的縣市，請確認地址是否正確")
        return None
    
    # 取得時間
    result = {}
    t = time.time()
    t1 = time.localtime(t)
    t2 = time.localtime(t + 10800)  # 三小時後
    now = time.strftime('%Y-%m-%dT%H:%M:%S', t1)
    now2 = time.strftime('%Y-%m-%dT%H:%M:%S', t2)
    
    # 建立 API URL
    url = f'https://opendata.cwa.gov.tw/api/v1/rest/datastore/{city_id}?Authorization={CWA_WEATHER_API}&elementName=天氣預報綜合描述&timeFrom={now}&timeTo={now2}'
    
    print(f"正在查詢 {city_name} 的天氣資料...")
    
    try:
        req = requests.get(url)
        data = req.json()
        
        # 除錯：印出 API 回應狀態
        print(f"API 狀態: {data.get('success', 'unknown')}")
        
        # 檢查 API 是否成功回傳
        if data.get('success') != 'true':
            print("API 回傳失敗")
            print(f"錯誤訊息: {json.dumps(data, ensure_ascii=False, indent=2)}")
            return None
        
        # 取得地區資訊
        location_name = data['records']['Locations'][0]['LocationsName']
        locations = data['records']['Locations'][0]['Location']

        area_keyword = None
        # 先按照區域名稱長度排序（長的優先），避免短名稱先匹配
        sorted_locations = sorted(locations, key=lambda x: len(x['LocationName']), reverse=True)
        for loc in sorted_locations:
            area = loc['LocationName']
            if area in address:
                area_keyword = area
                break
        
        if not area_keyword:
            print(f"\n找不到符合的區域，地址: {address}")
            print(f"可用的區域有:")
            for loc in locations:
                print(f"  - {loc['LocationName']}")
            return None
        
        # 找到符合的區域並取得天氣資訊
        for location in locations:
            area = location['LocationName']
            
            if area == area_keyword:
                print(f"\n查詢結果: {location_name} {area}")
                print("=" * 60)
                
                # 根據實際 JSON 結構解析
                weather_elements = location['WeatherElement']
                
                for element in weather_elements:
                    if element['ElementName'] == '天氣預報綜合描述':
                        time_list = element['Time']
                        
                        for time_period in time_list:
                            # 正確的鍵名是 StartTime 和 EndTime
                            start_time = time_period['StartTime']
                            end_time = time_period['EndTime']
                            
                            # ElementValue 是一個陣列，第一個元素包含 WeatherDescription
                            weather_desc = time_period['ElementValue'][0]['WeatherDescription']
                            print(f'這是weather forecast 函數內接收到的 :{weather_desc}\n')
                            prediction = f'「{location_name}{area}」未來3個小時天氣{weather_desc}'
                            return prediction
        return None   #無資料回傳 None
    except KeyError as e:
        print(f"JSON 鍵值錯誤: {e}")
        print("正在印出完整的 JSON 結構以供除錯...")
        if 'data' in locals():
            print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])  # 只印前2000字元
        return None
    except Exception as e:
        print(f"發生錯誤: {type(e).__name__} - {e}")
        return None

def cctv(msg):  # 即時影像監測
    try:
        output = ''
        camera_list = {
            '101' : 'https://www.youtube.com/live/z_fY1pj1VBw?si=xomei9bt8s0mUW0C',
            '陽明山' : 'https://youtu.be/d9KuXrPCWYU',
            '三仙台': 'https://youtu.be/dQ7Sd6PGLdA',
            '玉山': 'https://tw.live/cam/?id=ttjykzx',
            '阿里山': 'https://www.youtube.com/live/B6eki-0-w0g?si=extMBalIH_PHtEgW',
            '合歡山': 'https://cctv-ss04.thb.gov.tw/T14A-d61a0c91'
        }
        for item in camera_list:
            if msg == item:
                output = camera_list[msg]
    except Exception as e:
        print(e)
    return output

def air(address):   # 空氣品質監測
    result = {}
    url = f'https://data.moenv.gov.tw/api/v2/aqx_p_432?api_key={MOENV_API_KEY}&limit=1000&sort=ImportDate%20desc&format=JSON'
    req = requests.get(url)
    data = req.json()
    # print(data)
    records = data['records']
    for item in records:
        county = item['county']      # 縣市
        sitename = item['sitename']  # 區域
        aqi = int(item['aqi'])       # AQI 數值
        aqi_status = item['status']
        result[f'{county}{sitename}'] = [aqi, aqi_status]  # 記錄結果

    for i in result:
        if i in address:
            air_pred = f'AQI: {result[i][0]}，空氣品質{result[i][1]}\n'
            print(air_pred)
            return air_pred
            # print(f'新北市永和區: {result[i]}')   # 測試結果

def get_gemini_response(context_data):     # 請 gemini 當成氣象小幫手
    client = genai.Client(api_key=GEMINI_API_KEY) 
    # 組合給 Gemini 的完整提示 (Prompt)
    prompt = f"""
    你是 LINE 上的智慧助理，請根據以下提供的資訊，用中文和親切的語氣回答用戶的問題。

    根據爬蟲到的天氣狀況，簡短回覆就好，不超過30字，
    例如，
        冷: 「天氣冷，記得多加幾件衣服噢😶‍🌫️」
        晴朗： 「😎 完美的天氣！快出去玩吧！」
        陰雨： 「😫 又是濕答答的一天... 記得帶傘，小編為你感到難過！」
        ，開頭請以AI小幫手: 後面可以加關心您的話，可用一些小貼圖讓使用者更快了解天氣狀況
    
    提供的天氣資訊:
    {context_data}
    """
    
    try:
        # 呼叫 Gemini 模型
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        # 返回模型生成的文字
        return response.text
    except Exception as e:
        print(f"Gemini API 呼叫失敗: {e}")
        return "很抱歉，我的 AI 處理器目前遇到了一點問題，請稍後再試。"


@app.route("/callback", methods=['POST'])                     # call line bot 的 route
def linebot():
    body = request.get_data(as_text=True)                     # 取得收到的訊息內容
    try:
        line_bot_api = LineBotApi(ACCESS_TOKEN)               # 確認 token 是否正確
        line_handler = WebhookHandler(CHANNEL_SECRET)         # 確認 secret 是否正確
        signature = request.headers['X-Line-Signature']       # 加入回傳的 headers
        line_handler.handle(body, signature)                  # 綁定訊息回傳的相關資訊
        json_data = json.loads(body)                          # 轉換內容為 json 格式
        reply_token = json_data['events'][0]['replyToken']    # 取得回傳訊息的 Token ( reply message 使用 )
        user_id = json_data['events'][0]['source']['userId']  # 取得使用者 ID ( push message 使用 )
        print(json_data)                                      # 印出內容
        type = json_data['events'][0]['message']['type']
        if type == 'text':
            text = json_data['events'][0]['message']['text']
            if text == '雷達回波圖' or text == '雷達回波':
                line_bot_api.push_message(user_id, TextSendMessage(text='馬上找給你！抓取資料中....'))
                img_url = f'https://cwaopendata.s3.ap-northeast-1.amazonaws.com/Observation/O-A0058-001.png?{time.time_ns()}'
                img_message = ImageSendMessage(original_content_url=img_url, preview_image_url=img_url)
                line_bot_api.reply_message(reply_token, img_message)
            elif text == '地震':
                line_bot_api.push_message(user_id, TextSendMessage(text='馬上找給你！抓取資料中....'))
                reply = earthquake_information()
                text_message = TextSendMessage(text=reply[0])
                line_bot_api.reply_message(reply_token, text_message)
                line_bot_api.push_message(user_id, ImageSendMessage(original_content_url=reply[1], preview_image_url=reply[1]))
            else:
                reply = cctv(text)
                if not reply == '':
                    text_message = TextSendMessage(text=reply)
                    line_bot_api.reply_message(reply_token, text_message)
                    sec = math.ceil(time.time())
                    reply = reply + f'snapshot?t={sec}'
                    line_bot_api.push_message(user_id, ImageSendMessage(original_content_url=reply, preview_image_url=reply))
                else:
                    text_message = TextSendMessage(text=text)
                    line_bot_api.reply_message(reply_token, text_message)
        elif type == 'location':
            line_bot_api.push_message(user_id, TextSendMessage(text='馬上找給你！抓取資料中....'))
            address = json_data['events'][0]['message']['address'].replace('台','臺')  # 取出地址資訊，並將「台」換成「臺」
            reply_forcast = forecast(address)
            reply_aqi = air(address)

            forcast_msg = reply_forcast if isinstance(reply_forcast, str) else "⚠️ 天氣預報查詢失敗或查無資料。"
            aqi_msg = reply_aqi if isinstance(reply_aqi, str) else "☁️ 空氣品質查詢失敗或查無資料。"

            print(f'準備使用line回傳的結果: {forcast_msg} + {aqi_msg}\n')
            reply_all = f'{forcast_msg} \n\n {aqi_msg}'
            text_message = TextSendMessage(text=reply_all)
            line_bot_api.reply_message(reply_token, text_message)

            # gemini_input = f"{forcast_msg} {aqi_msg}" # 使用處理過的字串作為輸入
            # reply_gemini = get_gemini_response(gemini_input)
            # line_bot_api.push_message(user_id, TextSendMessage(text=reply_gemini)) 

    except Exception as e:
        print(e)
    return 'OK'     # 驗證 Webhook 使用，不能省略


# 建立圖文選單
configuration = Configuration(access_token=ACCESS_TOKEN)
def create_rich_menu():
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_blob_api = MessagingApiBlob(api_client)

        # 建立 richmenu
        headers = {
            'Authorization': 'Bearer ' + ACCESS_TOKEN,
            'Content-Type': 'application/json'
        }
        body = {
            "size": {
              "width": 2500,
              "height": 1686
            },
            "selected": True,
            "name": "圖文選單 1",
            "chatBarText": "查看更多天氣資訊",
            "areas": [
                {
                    "bounds": {
                      "x": 4,
                      "y": 2,
                      "width": 1648,
                      "height": 1684
                    },
                    "action": {
                      "type": "uri",
                      "uri": "https://line.me/R/nv/location/"
                    }
                },  
                {   
                    "bounds": {
                      "x": 1662,
                      "y": 2,
                      "width": 836,
                      "height": 840
                    },
                    "action": {
                      "type": "message",
                      "text": "雷達回波圖"
                    }
                },  
                {   
                    "bounds": {
                      "x": 1662,
                      "y": 850,
                      "width": 836,
                      "height": 836
                    },
                    "action": {
                      "type": "message",
                      "text": "地震"
                    }
                }
            ]
        }

        response = requests.post('https://api.line.me/v2/bot/richmenu', headers=headers, data=json.dumps(body).encode('utf-8'))
        response = response.json()
        print(response)
        rich_menu_id = response["richMenuId"]
        
        # 上傳 richmenu 圖片
        with open('static/weather_richmenu.png', 'rb') as image:
            line_bot_blob_api.set_rich_menu_image(
                rich_menu_id=rich_menu_id,
                body=bytearray(image.read()),
                _headers={'Content-Type': 'image/jpeg'}
            )

        line_bot_api.set_default_rich_menu(rich_menu_id)

# 啟動圖文選單
create_rich_menu()

if __name__ == "__main__":
    app.run()
    if GEMINI_API_KEY:  # 確認 gemini api key 存在
       print('OK for connecting gemini ~~')
    else:
       print("Gemini API Key 找不到，請檢查 .env 檔案。")
