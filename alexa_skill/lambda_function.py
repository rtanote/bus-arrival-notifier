from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_model.interfaces.alexa.presentation.apl import RenderDocumentDirective
import urllib.request
import json

# Backend URL - edit this to your Cloudflare Tunnel URL
BACKEND_URL = "https://your-tunnel-url.trycloudflare.com"


def create_apl_document(lines_with_colors):
    """APLドキュメントを動的に生成（複数行・色分け対応）"""
    text_items = [
        {
            "type": "Text",
            "text": "🚌 バス時刻表",
            "fontSize": "40dp",
            "fontWeight": "bold",
            "color": "white",
            "textAlign": "center",
            "paddingBottom": "30dp"
        }
    ]
    
    for line, color in lines_with_colors:
        text_items.append({
            "type": "Text",
            "text": line,
            "fontSize": "24dp",
            "color": color,
            "textAlign": "left",
            "width": "100%",
            "paddingBottom": "10dp",
            "fontFamily": "monospace"
        })
    
    return {
        "type": "APL",
        "version": "1.6",
        "mainTemplate": {
            "items": [
                {
                    "type": "Container",
                    "width": "100vw",
                    "height": "100vh",
                    "direction": "column",
                    "alignItems": "center",
                    "paddingTop": "40dp",
                    "paddingLeft": "40dp",
                    "paddingRight": "40dp",
                    "items": text_items
                }
            ]
        }
    }


def supports_apl(handler_input):
    try:
        supported = handler_input.request_envelope.context.system.device.supported_interfaces
        return supported.alexa_presentation_apl is not None
    except:
        return False


def format_display_lines(items):
    """display_itemsを行のリストに整形（ソート・色分け・幅揃え対応）"""
    # 最初のバスの残り時間でソート
    sorted_items = sorted(items, key=lambda x: x["buses"][0]["minutes"] if x.get("buses") else 999)
    
    # 最長の行き先名の文字数を取得
    max_chars = 0
    for item in sorted_items:
        route = item.get("route", "")
        if len(route) > max_chars:
            max_chars = len(route)
    
    lines_with_colors = []
    colors = ["#FFD700", "#00BFFF"]  # 黄色、水色
    
    for i, item in enumerate(sorted_items):
        route = item.get("route", "")
        buses = item.get("buses", [])
        if buses:
            # 全角スペースでパディング（日本語文字幅に合わせる）
            padding = "　" * (max_chars - len(route))  # 全角スペース U+3000
            
            # 時刻を揃えてフォーマット
            bus_texts = [f"{b['time']}({b['minutes']:2d}分)" for b in buses]
            line = f"【{route}】{padding} {' / '.join(bus_texts)}"
            color = colors[i % 2]
            lines_with_colors.append((line, color))
    
    if not lines_with_colors:
        lines_with_colors.append(("バス情報がありません", "white"))
    
    return lines_with_colors



class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)
    
    def handle(self, handler_input):
        speech = "バス時刻スキルです。あとなんぷん、と聞いてください。"
        return handler_input.response_builder.speak(speech).ask(speech).response


class GetBusTimeIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("GetBusTimeIntent")(handler_input)
    
    def handle(self, handler_input):
        speech = "バス情報を取得できませんでした"
        display_items = []
        
        try:
            url = f"{BACKEND_URL}/bus/speech"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode('utf-8'))
                speech = data.get("speech", "バス情報を取得できませんでした")
                display_items = data.get("display_items", [])

            activate_url = f"{BACKEND_URL}/lametric/activate"
            activate_req = urllib.request.Request(activate_url)
            urllib.request.urlopen(activate_req, timeout=5)
        
        except Exception as e:
            speech = "エラーが発生しました"
        
        response_builder = handler_input.response_builder
        response_builder.speak(speech)
        
        if supports_apl(handler_input):
            lines_with_colors = format_display_lines(display_items)
            response_builder.add_directive(
                RenderDocumentDirective(
                    token="busToken",
                    document=create_apl_document(lines_with_colors),
                    datasources={}
                )
            )
        
        return response_builder.response


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)
    
    def handle(self, handler_input):
        speech = "あとなんぷん、と聞いてください。"
        return handler_input.response_builder.speak(speech).ask(speech).response


class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return (is_intent_name("AMAZON.CancelIntent")(handler_input) or
                is_intent_name("AMAZON.StopIntent")(handler_input))
    
    def handle(self, handler_input):
        return handler_input.response_builder.speak("さようなら").response


class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)
    
    def handle(self, handler_input):
        speech = "すみません、よく分かりませんでした。あとなんぷん、と聞いてください。"
        return handler_input.response_builder.speak(speech).ask(speech).response


class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("SessionEndedRequest")(handler_input)
    
    def handle(self, handler_input):
        return handler_input.response_builder.response


class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True
    
    def handle(self, handler_input, exception):
        speech = "エラーが発生しました。もう一度お試しください。"
        return handler_input.response_builder.speak(speech).ask(speech).response


sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(GetBusTimeIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()