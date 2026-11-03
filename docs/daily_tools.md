# 本地相册与分组拼音

2026-11-01输入与按钮v9已独立部署并通过10分钟混合真实眼控检查，用户确认84次选择主动、输入收藏符合意图、音画进度正常。新增常用整句之后实际拼出“你好”，原收藏保留；完整结果及新流程见[输入效率与按钮美化](ui_typing.md)。下方v8分组流程和结果为历史。

用户已确认合并第3、4项：三张自然风景示例相册，以及可组合中文的分组拼音输入。均仅在本机屏幕展示，不向手机或无线接收端发送。自定义文字暂不转语音；帮助继续播放原来的“请来帮助我”。视频仍是后续预研。

入口：“更多→相册表情→本地相册”或“更多→快捷交流→文字输入”。表情心意移到相册表情内，原六张与返回逻辑保留。原四个眼控区域、1秒停留、300ms有效移开、失效清零、防连选、辅助暂停和重新定位保持。每次字母分组、选字、翻页都重新释放和停留。

相册先选择上一张/下一张，再选查看大图。观赏页只在右下保留“返回控制”，不会直接换图；看向右下仍可能打开控制页，因此不能称为全屏无交互观赏。首批山间远眺、湖畔雪山、林间阳光，608×296 RGB565每张359936字节，共1.08MB；只缓存一张图，最多32张。控制页保留大目标，不自动轮播。

输入流程：选择输入拼音→逐层选字母→拼完一个音节后返回→选字。每页两个候选，左下下一组，右下返回；选字后清空拼音并加入正文。ü输入v，不输入声调；第一版逐字输入，不支持整句拼音、词语联想或自由光标。字库包含从词频数据选出的5000个汉字、411个音节及标点数字，不宣称覆盖所有汉字；多音字按首列读音优先、再按词频排序。

正文最多32字，拼音最多6个字母。“编辑收藏→修改文字”提供删除（先删未完成拼音，再删正文）、标点数字、确认清空；“展示收藏”提供大字展示、收藏本句和帮助。“常用句”最多12句，可显示、确认载入替换草稿、确认删除。收藏写入独立的data/private/favorites.json，临时文件写入/fsync后原子替换；保存失败提示且保留草稿与原收藏。升级包不包含收藏或个人音量设置。草稿仅在本次运行内保留，返回菜单和BTN2重新定位不会丢弃；退出程序或断电后未收藏草稿不保留。运行日志只记动作与长度，不写正文；收藏本身是本地明文个人数据。

需完整UI v8源码与素材。使用显式参数 `--daily-tools --emotion-cards --music --quick-phrases --reposition-assist`，无线保持off。默认不启用新功能。确认板卡空闲、摄像头/屏幕/AUX正常后，在独立升级目录手动启动：

```bash
cd /home/xilinx/Eye_Tracker_Upgrade_Version
sudo ./tools/run_eye.sh --profile data/private/profiles/upgrade_check.json --music --quick-phrases --emotion-cards --daily-tools --reposition-assist
```

照片在开发机升级目录内导入，不需要拔SD、格式化或改启动镜像。示例：

```powershell
& '<user-home>/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' tools/import_photos.py '<project>/my_photos/example.jpg' --id mountains --title '我的风景' --replace
& '<user-home>/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' tools/build_text_assets.py
```

替换要求显式--replace；导入会处理EXIF方向、缩放留边、去除源元数据并转换RGB565。新标题需重新生成字形素材，随后生成独立升级包、空闲时同步。不要直接覆盖正在运行的板端素材。

来源：山景[Hannes Röst / Fronalpstock](https://commons.wikimedia.org/wiki/File:Fronalpstock_big.jpg)，CC BY-SA 3.0，缩放与RGB565衍生文件继续同许可；湖景[Paul Stewart / Lake Mapourika](https://commons.wikimedia.org/wiki/File:Lake_Mapourika1.jpg)及林景[SpessiG / Landscape of a wild forest](https://commons.wikimedia.org/wiki/File:Landscape_of_a_wild_forest.jpg)，CC0。完整来源与修改说明在assets/photos/album.json。读音数据来自[mozillazg/pinyin-data](https://github.com/mozillazg/pinyin-data)，频率来自[fxsjy/jieba](https://github.com/fxsjy/jieba)，均MIT；固定版本、变换规则及两份完整许可保存在assets/typing。只用静态数据，不在板上安装网络输入法或jieba。

验证结果（2026-10-31，当前UI v8）：424项软件检查通过，原位流、个人模型、识别门限和所有音频文件不变。

| 真人检查 | 实际完成范围 |
| --- | --- |
| 相册返回补测，120.017秒/988帧/16选择 | 3次查看大图后正常返回，用户确认无需BTN2；三张风景此前均已查看 |
| 初次输入，300.030秒/2251帧/19选择 | 用户选出“你”，“好”未在时限内完成 |
| 输入收藏，600.108秒/4598帧/55选择 | 输入“你”、确认清空流程、收藏、大字展示及返回；用户确认均主动且正常 |
| 收藏载入，180.041秒/1336帧/17选择 | 新进程读回收藏，确认载入“你”，删除正文；用户确认均主动、响应正常，收藏文件哈希不变 |

三个输入轮次各使用过一次BTN2辅助重新定位；不称为无需辅助的持续输入。正常结束轮次坏行/坏帧均1→1，音频/DMA正常清理，无复位或重启。10分钟轮次RSS采样218324–233324KiB，含有界日志/缓存增长，不构成20分钟或无泄漏证明。1条收藏经独立预检及下一次真人运行读回；未做断电/重启持久化试验。497张保留的交互图已审阅；跨6个证据包累计核对854个文件条目，其中元数据存在重复，不当作854个独立文件。结果见build/daily_tools_20261031/result.json。

本阶段保留两次有用失败：最初逐帧文字混合中位114.3ms，使相册相邻帧中位166.8ms，超过原150ms连续输入保护，进度反复清零；改为只缓存当前页后，板端暖绘制约11.4ms，进度恢复。随后大图返回文字偏离原右下注视点，用户只能BTN2退出；返回改为浅底、文字居中于(472,336)，三次实际返回通过。照片尺寸、命中区域和模型门限未改，翻页冷绘制仍较慢；首轮中断exit1/KeyboardInterrupt保留，不记为通过。

当前真人输入证据仅为单字“你”，未完成“你好”或更长句子的输入效率验证；32字/12条上限、确认删除收藏、保存失败处理及新文本页面帮助仅有软件检查，尚未真人覆盖。本阶段未做新20分钟、随机准确率、通用自动恢复或无线整链验收，不沿用历史音乐20分钟结论。普通室内光、补光灯关闭、当前个人模型和有限头动条件仍适用。

当前完整私有包：build/daily_tools_20261031/eye_tracker_upgrade_daily_tools_verified.zip，包含个人模型，禁止公开；最终仅同步说明和清单，运行代码与已测版本一致。收藏和个人音乐音量不随升级覆盖。标准手动服务参数保持原样，新功能仍需显式参数。
