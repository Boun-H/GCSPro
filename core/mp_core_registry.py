from dataclasses import dataclass


@dataclass(frozen=True)
class MPFeature:
    key: str
    label: str
    group: str
    description: str = ""


# MP核心功能注册表：用于自动生成工作台UI和动作分发。
MP_CORE_FEATURES: tuple[MPFeature, ...] = (
    MPFeature("connection.open", "连接飞控", "连接", "打开连接对话框"),
    MPFeature("connection.disconnect", "断开连接", "连接", "主动断开当前连接"),
    MPFeature("connection.reconnect", "快速重连", "连接", "按最近一次成功链路重新连接"),
    MPFeature("connection.panel", "链路面板", "连接", "查看并切换当前活动链路"),
    MPFeature("connection.settings", "链路设置", "连接", "打开通信链路配置中心"),
    MPFeature("vehicle.panel", "多机管理", "载具", "打开载具列表并切换当前载具"),
    MPFeature("setup.open", "Vehicle Setup", "Setup", "打开 Vehicle Setup 总览"),
    MPFeature("setup.sensors", "Sensors", "Setup", "打开传感器与校准入口"),
    MPFeature("setup.power", "Power", "Setup", "打开电源与电池设置"),
    MPFeature("setup.firmware", "Firmware Upgrade", "Setup", "请求进入固件升级流程"),
    MPFeature("params.open", "参数面板", "参数", "打开参数读取与写入面板"),
    MPFeature("params.refresh", "读取参数", "参数", "从飞控读取全部参数"),
    MPFeature("params.save", "写入参数", "参数", "将已修改参数写回飞控"),
    MPFeature("mission.toggle_add", "点选航点", "任务", "切换地图点选航点模式"),
    MPFeature("mission.fit_route", "全览航线", "任务", "缩放到全部任务航点"),
    MPFeature("mission.batch_insert", "批量插入", "任务", "在选中航点后批量插入新任务点"),
    MPFeature("mission.batch_delete", "批量删除", "任务", "批量删除选中的任务航点"),
    MPFeature("mission.reverse", "航线反转", "任务", "反转当前任务航线顺序"),
    MPFeature("mission.clear", "清空任务", "任务", "清空当前任务航点"),
    MPFeature("mission.uniform_alt", "统一高度", "任务", "批量设置任务点高度"),
    MPFeature("mission.set_home_vehicle", "H点=飞机位置", "任务", "将H点设置为飞机实时位置"),
    MPFeature("mission.set_home_map", "地图选H点", "任务", "进入地图点击选取H点模式"),
    MPFeature("mission.download", "下载任务", "任务", "从飞控下载任务航线"),
    MPFeature("mission.upload", "上传任务", "任务", "向飞控上传任务航线"),
    MPFeature("map.toggle_measure", "测距模式", "地图", "切换地图测距模式"),
    MPFeature("map.clear_measure", "清空测距", "地图", "清空当前测距并退出测距模式"),
    MPFeature("map.locate_aircraft", "定位飞机", "地图", "地图中心定位到飞机位置"),
    MPFeature("map.toggle_follow", "飞机跟随", "地图", "切换飞机居中跟随"),
    MPFeature("flight.arm", "解锁ARM", "飞控", "下发解锁指令"),
    MPFeature("flight.disarm", "上锁DISARM", "飞控", "下发上锁指令"),
    MPFeature("flight.takeoff", "起飞10m", "飞控", "下发起飞指令"),
    MPFeature("flight.land", "降落LAND", "飞控", "下发降落指令"),
    MPFeature("flight.rtl", "返航RTL", "飞控", "下发返航指令"),
    MPFeature("fly.view", "Fly View", "Fly", "打开飞行视图工具面板"),
    MPFeature("fly.guided_hold", "Guided Hold", "Fly", "切换到悬停等待"),
    MPFeature("fly.guided_resume", "继续任务", "Fly", "恢复 AUTO 任务执行"),
    MPFeature("analyze.open", "Analyze", "Analyze", "打开 MAVLink Inspector 与日志工具"),
    MPFeature("analyze.refresh", "刷新Inspector", "Analyze", "刷新遥测快照与日志列表"),
    MPFeature("analyze.download_logs", "下载/查看日志", "Analyze", "查看本地日志目录并准备回放"),
    MPFeature("peripheral.open", "外围能力", "Peripheral", "打开 Joystick / ADS-B / RTK 配置"),
    MPFeature("peripheral.save", "保存外围配置", "Peripheral", "保存视频、插件与外设设置"),
    MPFeature("peripheral.rtk", "RTK/GPS 注入", "Peripheral", "向当前载具写入 RTK/GPS 位置"),
)


def grouped_features() -> dict[str, list[MPFeature]]:
    groups: dict[str, list[MPFeature]] = {}
    for feature in MP_CORE_FEATURES:
        groups.setdefault(feature.group, []).append(feature)
    return groups
