# 板载音频与辅助按键

阶段3最新软件：双页六句已实现、358项软件测试通过；超过2.048秒的固定语音复用v2双缓冲，其余短句保留原模式。见[双页交流](quick_phrases.md)。原三句WAV未改，新六句未上板听音；下文旧阶段测试数按各自版本解释。

升级版2026-10-29：当前源码/位流为音频IP v2（0x00020000），增加连续双缓冲、暂停恢复和音乐抢占，仍兼容下述短语模式。342项软件测试和两项XSim通过，新位流未上板或听音；当前规范见[音乐升级](music.md)。下方v1寄存器、性能和听音记录属于历史基线，不能替代v2验收。

2026-10-22。音频线已到；用户确认三段中文语音清楚。已加入显式听音与“合成停留→语音→实体键中止”联调入口，板测结果以build/board/result.json为准。不是实际眼控验收。

## 连接与使用

复用纽曼BS02。只需一根普通3.5mm TRS立体声公对公AUX线，两头均为两个绝缘环，约1米；板卡MIC+HP耳机输出接音箱AUX输入。LINE_IN是输入，不能作为输出；无需USB声卡、新音箱或蓝牙。用户于10月22日确认线已到并已接好。插线前保持停止播放，音箱音量先低；首轮三句清晰度已由用户确认。

BTN0暂停/恢复；BTN1取消当前停留并中止正在播放的语音；BTN2清除校准、禁止继续选择；BTN3退出。BTN2不伪造新校准，恢复键也不能绕过校准。按键30ms防抖，启动时已按住/采样中断后已按住不补造事件；多键同时触发依次优先退出、清校准、暂停、取消。按键是辅助人员操作入口，最终选择仍由有效视线驱动。

## 硬件与软件

- audio_aux_axi通过独立AXI-Lite接口接PS，基址0x43C20000、范围128KiB；相机和VDMA地址不变。
- 0x00000: AUD1身份；0x00004:版本0x00010000；0x00008:命令START=1/STOP=2/CLEAR=4；0x0000C: busy/done/fault/clock_alive依次bit0..3。
- 0x00010:16kHz单声道样本数1..32768；0x00014:样本索引；0x00018:I2C拉低控制；0x0001C:SDA/SCL/MCLK锁定输入；0x00020:BTN3..0；0x00024:LRCLK计数；0x00028:BCLK计数。
- 0x10000..0x1FFFF:64KiB BRAM，两个有符号PCM16样本/32位字，小端；播放前完整写入并读回，播放期间硬件拒绝改写/重启/改长度。不使用音频DMA，PS调度停顿不改变播放速度。
- ADAU1761地址0x3B；专用开漏I2C。10MHz MCLK来自独立时钟IP，codec PLL配置49.152MHz、主模式48kHz、64个BCLK/帧。16kHz短语每样本重复三个48kHz帧，双声道相同，24位I2S数据低8位为0。
- 自定义串行器在50MHz域同步外部BCLK/LRCLK，实际输出路径限制25ns；低速异步输入仅豁免到第一级同步器，未整体豁免音频输出时序。export脚本检查端点和audio_output.rpt。
- 软件默认配置模拟输出静音；数字播放完自动停，显式取消/退出立即清输出。BCLK中断或MCLK失锁硬件终止，软件播放截止时间为短语时长+250ms。清理时先停硬件，再尝试静音两侧输出/混音器；任何失败保留报告。

本地短语water.wav“我想喝水”、rest.wav“我想休息”、help.wav“请来帮助我”，由本机Windows SAPI Microsoft Huihui Desktop以16kHz/16bit/mono生成（SpAudioFormat.Type=18，Rate=0），去除额外元数据，峰值缩放至不高于8191。manifest绑定文字、样本数和SHA256。板上只读WAV，不需要TTS、网络或电脑。保底版曾按用户听感从-24dB逐步提高到-6dB（左右0xCF），用户确认合适且暂停恢复没有旧句续播。

2026-10-29升级版单句试听中音量偏小，逐档比较期间用户发现音箱没电关机；该组音量比较不作结论。用户恢复音箱供电/AUX后，重新播放完整“请帮我换个姿势”，确认0dB音量合适、声音清楚；仅升级版正式输出改为左右0xE7并回读。WAV字节未放大、峰值界限不变，保底源码未改。依据[ADAU1761 Rev F R29/R30](https://www.analog.com/media/en/technical-documentation/data-sheets/adau1761.pdf)，音量域每步1dB；寄存器读回不等于实测声压。音箱自身音量与供电状态单独确认，退出时恢复静音。记录见build/upgrade_deploy_20261029/result.json。

## 验证入口

- fpga/scripts/simulate_audio.tcl：真实串行波形解码、正负样本、左右声道/三次重复、AXI背压和写保护、停止、失钟静音、复位及I2C。
- tests/test_auxiliary.py：本地短语身份、超时、PCM装载、I2C、按键、清校准后禁选。
- bash tools/run_board.sh audio-test --load --output data/private/bringup/audio：全程模拟输出静音，验证codec寄存器回读、PLL锁定、48kHz/64时钟、三个短语完成和显式停止，同时显示测试UI。不是听音测试。
- bash tools/run_board.sh control-test --load --seconds 75 --output data/private/bringup/controls：程序坐标在喝水/休息间切换；实际BTN0..3控制同一停留控制器；不打开真实眼控或语音。BTN3退出或超时均正常停机，随后黑屏。

## 真实声音与交互联调

默认不传--audible时保持既有静音验收行为。audio-test、control-test及证据核验后的eye-trial允许--audible，其他模式拒绝此参数。eye-trial默认仍静音。

- bash tools/run_board.sh audio-test --load --audible --output data/private/bringup/audio_listen：依次播放三段短语，句间停约1秒；任何辅助按键中止，退出静音。日志不自行宣称听觉合格，听感由用户反馈单独记录。
- bash tools/run_board.sh control-test --load --audible --seconds 75 --output data/private/bringup/speech_controls：每5秒有效演示时间换一个程序目标，形成真实停留事件后播报对应WAV；暂停时模拟目标也停止推进，恢复后原目标额外保持3秒，便于检查没有旧句续播；界面始终标注“测试输入·非真实眼控”，并显示正在播报的文字。
- 播报期间不累计新目标的停留、不排队播报；完成后必须重新累计完整停留。相同目标持续输入仍被控制器锁定。BTN0暂停/恢复、BTN1取消、BTN2清校准、BTN3退出均先停止声音；中断的短语不会在恢复后续播或补播。清校准后继续禁止选择。
- 硬件播放错误、显示异常或正常退出都尝试停止播放并静音，保存未完成轨迹。126项软件检查包括声音默认关闭、三句播放、中途按键、持续目标防重复、显示异常后停止及重复初始化PLL；实际按键与听感以板测和用户观察分别记录。

## 参考依据

原理图references/pynq_z2_schematic.pdf第7页codec、第11页按键。音频MCLK U5、BCLK R18、LRCLK T17、DAC_SDATA G18、SDA T9、SCL U9；按钮D19/D20/L20/L19。ADC与录音不启用。

[Analog Devices ADAU1761数据手册](https://www.analog.com/media/en/technical-documentation/data-sheets/ADAU1761.pdf)定义寄存器与I2S时序；[PYNQ官方音频参考](https://github.com/Xilinx/PYNQ/tree/d90670c69f7b71ea1a5d23aaa3e0ec713ff5fa9f/pynq/lib/_pynq/_audio)用于核对PLL和输出路由。下载来源及哈希在references/audio/sources.json；保留原许可证。当前IP与驱动独立实现，不使用旧UIO固定地址驱动，也不覆盖相机寄存器。

首次板测发现两处配置错误，已修正：BCLK实际为R18、LRCLK为T17，初稿曾对调；Linux启动的IO PLL与Vivado默认PS预设不同，PYNQ套用HWH分频后FCLK0/1实为31.25/62.5MHz，音频LRCLK因此仅30kHz。现在每次fresh overlay加载后、访问DMA前，使用PYNQ Clocks按频率重新计算PL分频，要求读回50/100MHz；CPU/DDR PLL不改动。任何频率不符立即拒绝运行。新位流须重新验证视频；历史视频结果保留当时条件，不改写为新时钟结果。

重复加载修复（2026-10-22）：Overlay重载会中断MCLK，直接重写PLLEN=1曾无法重新锁定；现在先关闭核心和PLL、写入参数、启动PLL、限时等待锁定，再启用核心。LOCK是只读状态位，板上观察PLLEN=0时仍可能读到LOCK=1，参数回读仅屏蔽这一状态位，所有可写位继续严格核对。核心未就绪时清理仅关闭核心，不访问尚不可用的音量寄存器，并保留原始错误。修复后静音audio-test及随后有声control-test两次Overlay加载均通过初始化，无需断电。


## 2026-10-26 真实四区域眼控语音

新增eye-trial --audible：使用同一个已通过独立检查的私有模型、五张新中心参考及真实相机输入形成停留事件，才播放对应本地WAV。仍是普通室内光、当次校准、有限头动的实验入口，不是PCCR或通用个人校准。默认不开声音，不启用UART。语音增益和素材保持此前用户认可的配置。

喝水、休息、帮助各播一句；更多及返回不播音。选中后短语可正常播完，不因正常眨眼被截断；显式取消、暂停、清校准、退出会停音，恢复不续播、不补播。播音期间继续获取和记录眼图，但不累计新目标停留或排队；持续注视同一目标仍受锁定保护。开始播音前核对live来源、当前校准、唯一源时刻、输入年龄、短语身份，按键在采集前后及特征处理后优先处理。

第一轮appearance_speech_20261026已完成：384交互帧、17次选择，其中11句完整播放、6次更多/返回静音；156张播音中眼图无新停留或选择。用户确认三句对应正确、清楚且音量合适，持续看喝水不重复播报、导航无声音，无误选且画面稳定。结果和范围在该目录assessment.json。旧音频bit/HWH、识别模型和门限未变。

用户不便操作板上按键，因此新增显式--trial-auto-controls，仅允许与eye-trial --audible合用。第一句真实眼控短语播报约0.6秒后自动cancel；第二句真实短语约0.6秒后自动pause，两秒后resume。辅助命令记录source=automatic_test；不会生成眼图、候选或选择，也不伪称实体按键验收。普通入口不会自动中断。现场实体按键电气/防抖验证沿用此前记录；当前本地275项软件检查包括真实输入接口、持有目标防重复、各辅助命令停音、自动测试调度和异常清理。实时自动中断听音结果以本轮最终assessment为准。

自动中断上板结果：appearance_speech_controls_20261026记录喝水取消、帮助暂停及恢复；恢复后4.382秒无新声音，再由新的休息选择播报。用户确认两次停音、恢复后约3秒安静且无旧句续播，画面及后续选择正常。本轮并未操作实体按钮。两轮最终停止音频并静音、双DMA停机，详细记录见各assessment.json。
