# 通用 PYNQ Skill（独立复用模块）

**名称：`pynq-portable-verification`。** 适用于基于 PYNQ 的 Overlay 接口核对、
简单 AXI DMA 数据传输、参考结果对比及资源时序证据整理，不依赖眼控算法或个人模型。
此目录对应赛题指南 3.3.5.2 的 Skill 提交项，也对应“通用 PYNQ Skill”独立加分项；
是否得分由赛事评审决定。

## 使用方法

1. 将 `pynq-portable-verification/` 整个目录复制到智能体的技能目录，或直接让智能体读取其中 `SKILL.md`。
2. 提供当前板卡、Overlay 与接口定义；可使用提示：“用 pynq-portable-verification 检查这份 Overlay 契约，先做离线核对，再给出 DMA 验证步骤。”
3. 不使用智能体时，三个 Python 脚本也可独立运行，仅需 Python 3.10+。

```bash
python skill/pynq-portable-verification/scripts/overlay_contract.py skill/pynq-portable-verification/examples/contract_a.json skill/pynq-portable-verification/examples/observed_a.json
python skill/pynq-portable-verification/scripts/verify_results.py skill/pynq-portable-verification/examples/results.json
python -m unittest discover -s skill/pynq-portable-verification/tests -v
```

## 可交付能力

| 工作流 | 输入 | 输出与失败条件 |
|---|---|---|
| Overlay 契约核对 | 平台、IP、地址、寄存器、时钟、bit/HWH 哈希 | JSON 差异；不匹配返回非零退出码 |
| DMA 缓存与生命周期 | 已配置的简单 DMA、连续缓冲区、长度、超时、恢复回调 | 完成字节数；错误/超时保留缓冲区所有权 |
| Golden 与指标检查 | 参考值、实际值、误差容限、时延、实现指标 | 全形状/有限性/误差统计与约束检查 |

接口名、基地址、长度和时钟均由调用方提供。两个示例刻意采用不同平台与地址布局。
不支持将简单 DMA 适配器直接用于 VDMA、SG、循环 DMA；不在脚本中隐式烧写位流或修改系统配置。

## 来源及验证效果

技能来自本队伍在多版本 Overlay 管理、DMA 退出清理、按钮轮询阻塞及 AI 参考核对中的经验。
详见 `references/provenance.md` 的“观察—规则—检查”对应表。
`tests/test_helpers.py` 验证正常路径及不匹配、超时、部分启动、恢复失败等路径；
测试结果见 `report/skill_tests.txt`（仓库根目录）。这些是可复现离线检查，不等同于新板卡实测。

许可证：MIT；依赖的 PYNQ 接口文档由原项目维护。
