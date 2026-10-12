# 数据来源与核对记录

核对日期：2026-10-12。

## 离线图鉴

- [洛克王国世界 WIKI 精灵图鉴](https://wiki.biligame.com/rocom/%E7%B2%BE%E7%81%B5%E5%9B%BE%E9%89%B4)：上游社区图鉴。
- [JayeGT002/rocom-wiki-data](https://github.com/JayeGT002/rocom-wiki-data)：WIKI 数据镜像及结构化 JSON；本地快照取自该项目的 [pets.json](https://jayegt002.github.io/rocom-wiki-data/data/pets.json)，仓库提交 `6ab264cb98eec1dd2dde0d7c6dfa200733a98d63`。本项目只保留查询所需字段，去除描述、图片等字段。
- [WIKI 孵蛋组别查询](https://wiki.biligame.com/rocom/%E5%AD%B5%E8%9B%8B%E7%BB%84%E5%88%AB%E6%9F%A5%E8%AF%A2)：未发现组不参与配对。

图鉴衍生数据沿用上游声明的 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.zh-hans)；请保留 WIKI 来源、上游仓库和本文件署名。游戏名称和数据版权归原权利方。本项目没有打包游戏图像或音频。

## 生蛋规则

- [WIKI 奖牌图鉴](https://wiki.biligame.com/nrc/%E5%A5%96%E7%89%8C%E5%9B%BE%E9%89%B4)：大块头/小不点与体型、婉转声/粗嗓门与声音有关；部分奖牌与地点或时间有关。
- [WIKI 精灵图鉴实例](https://wiki.biligame.com/nrc/%E5%B7%A8%E9%BC%93%E8%B1%A1)：上游同时列有成年精灵体重范围和精灵蛋重量阈值。本地只保留成年精灵体重范围；蛋重阈值不用于本工具计算。
- [玩家体型讨论](https://www.taptap.cn/moment/844744598214412822?group_id=228326)：仅身高、体重显示为满值也可能没有大块头牌，说明成年体型的判牌需要谨慎估计。
- [游民星空玩家生蛋介绍](https://www.gamersky.com/handbook/202604/2116160.shtml)：蛋的物种由母方决定；亲本有异色、炫彩会提高特殊蛋机会。
- [社区繁殖介绍](https://rocokingdomworld.org/zh-hant/guides/breeding-system/)：一公一母、共享蛋组，母方定种。
- [玩家声体继承研究视频](https://www.bilibili.com/video/BV19kj36cEcx/)：可作进一步人工核查，当前未从视频提取精确公式。

## 概率处理

- [玩家整理的游戏配置](https://github.com/mieli1722/roco_kingdom_world_conf/blob/main/PET_GLOBAL_CONFIG.json)：`pet_inheritance_ex_shining_rate_male/female=72`、`pet_inheritance_im_shining_rate=100`、`pet_inheritance_ex_glass_rate_male/female=36`、`pet_inheritance_personality_rate_male/female=3000`。按万分比解读为异色亲本各 0.72%、隐性异色约 1%、炫彩亲本各 0.36%、完整性格随父母各 30%。[玩家整理](https://www.4399.com/pcgame/topic/53477756.html)中的外观数字相符；[性格机制整理](https://www.233leyuan.com/post-detail/2053039458908291072)也报 30%/30%/40%。配置未给完整的服务器判定顺序，软件假设未出现显性异色与显性炫彩才属于普通蛋，并在此条件下分别估算两种隐性概率。
- [性格图鉴](https://wiki.biligame.com/rocom/%E6%80%A7%E6%A0%BC)：30 个原始性格与加成、减益属性对应；软件按完整性格遗传，再分别查询 + 或 −。随机性格暂按 30 种均匀分配。
- [音碟吼蛋重表](https://wiki.biligame.com/nrc/%E9%9F%B3%E7%A2%9F%E5%90%BC)：蛋重 2.940–7.040 kg，小不点 ≤3.022 kg，大块头 ≥6.958 kg，恰为区间两端各 2%。该证据针对蛋重；成年精灵判牌只是同口径的估算。
- [玩家抓包项目记录](https://github.com/whoisnian/rocom-capture/blob/master/HISTORY.md)描述体重围绕双亲百分比均值浮动、声音基本取双亲均值。其记录没有给出准确幅度；因此体型遗传的 ±2% **未查明具体出处**，作为可修改假设。
- 普通蛋隐性炫彩默认 **1% 未查明具体出处**。声音奖牌组合默认值（同侧 90%、一侧 2%、相反每侧 0%、双无牌每侧 0.5%）只是为规划路线设定的对称模型，**没有游戏实测概率依据**，均可修改或恢复默认。
