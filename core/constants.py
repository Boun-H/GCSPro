SYSTEM_STATUS_MAP = {
    0: "未启动",1: "启动中",2: "待机",3: "主动飞行",
    4: "关键",5: "应急",6: "手动",7: "校准",8: "退出",9: "终止"
}
MAP_SOURCES = {
    '谷歌卫星': {'tiles': 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}','attr': 'Google'},
    'ArcGIS卫星': {'tiles': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}','attr': 'Esri'}
}
BAUD_RATES = ["9600", "57600", "115200", "230400", "460800", "921600"]
DEFAULT_BAUD = "115200"
DEFAULT_LAT = 22.523393
DEFAULT_LON = 118.663749
DEFAULT_ZOOM = 5
BATTERY_WARN = 30
LOST_HEARTBEAT = 3

LOW_BATTERY_CRITICAL = 25
LOW_BATTERY_WARN = 45
GPS_CRITICAL = 6
GPS_WARN = 10

MODE_AUTO = "AUTO"
MODE_GUIDED = "GUIDED"
MODE_QGUIDED = "QGUIDED"
MODE_QLOITER = "QLOITER"
MODE_QRTL = "QRTL"
MODE_RTL = "RTL"

READY_FLIGHT_MODES = {MODE_AUTO, MODE_GUIDED, MODE_QGUIDED, MODE_QLOITER}
LINK_WARNING_TOKENS = ("异常", "断开", "高延迟", "timeout", "disconnected")
