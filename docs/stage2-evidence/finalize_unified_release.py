"""Publish current status after recorded real acceptance, without touching historical evidence."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs/stage2-evidence'
state = json.loads((EVIDENCE / 'stage7-default-final-state.json').read_text(encoding='utf-8'))
assert state['oldTasksUnchanged'] == 12 and state['validatedCritiqueClaims'] == 7
assert state['newOperationAndResultUnchanged'] and state['newArtifactAndMessagesUnchanged']
assert '303 passed' in (EVIDENCE / 'stage7-default-tests.log').read_text(encoding='utf-8')
assert 'built in' in (EVIDENCE / 'stage7-default-build.log').read_text(encoding='utf-8')

def edit(relative, transform):
    path = ROOT / relative
    path.write_text(transform(path.read_text(encoding='utf-8-sig')), encoding='utf-8')

for version in ('v24', 'v25', 'v26'):
    path = EVIDENCE / f'stage4-analysis-{version}-case-plan.json'
    plan = json.loads(path.read_text(encoding='utf-8-sig'))
    assert plan['casesExecuted'] == 1
    plan['status'] = 'executed_once'
    plan['actualStatus'] = 'failed' if version == 'v25' else 'succeeded'
    if version != 'v25':
        plan['partial'] = version == 'v24'
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

edit('README.md', lambda text: text.replace(
    '统一任务界面正在重构，预览入口为 `http://localhost:5173/?unified=1`。当前操作与运行说明见 [统一任务指南](docs/UNIFIED_TASK_GUIDE.md)，已验与未通过项见 [完整验收台账](docs/STAGE7_ACCEPTANCE.md)。阶段4–7尚未整体验收；下方旧入口能力介绍不代表新实现已经完成最终验收。',
    '统一任务界面已成为默认入口：`http://localhost:5173/`。阶段0–7按当前设计范围验收，操作与运行说明见 [统一任务指南](docs/UNIFIED_TASK_GUIDE.md)，范围和限制见 [完整验收台账](docs/STAGE7_ACCEPTANCE.md)及[正式入口验收](docs/STAGE7_FINAL_RELEASE.md)。`?unified=0`保留旧界面回退；下方旧入口能力介绍不扩大新版验收范围。'))

def acceptance(text):
    text = text.replace('状态：未通过，统一界面尚未切换为正式默认入口。', '状态：当前设计边界通过，统一界面已切换为正式默认入口。')
    text = text.replace('阶段0–3、5、6已分别验收，阶段4、7仍未整体完成。', '阶段0–7已按当前范围分别验收。')
    current = ('阶段4最新真实v26批判完整成功，7条判断均通过逐项数值/引用与人工内容核对；阶段7根地址、论文刷新恢复、成果重开、旧入口及共享路径兼容实际通过。切换后前端303项、类型/生产构建通过；Python最终262项，Java既有48项适用未变契约。12旧任务11收据保持，本轮共3个固定模型案例各一次，累计40例，统一授权已记录。详见STAGE4_ACCEPTANCE.md及STAGE7_FINAL_RELEASE.md。\n\n')
    start = text.index('阶段5按当前范围通过')
    end = text.index('2026-10-10最新范围：', start)
    text = text[:start] + current + text[end:]
    text = text.replace('最新v7三例已在用户', '## 历史执行记录\n\n下列批次中的待授权、未通过和旧门槛仅反映当时状态，以本文件当前矩阵及最终报告为准。\n\n最新v7三例已在用户', 1)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith('| A01 '):
            lines[index] = '| A01 单一入口三栏 | 真实已验 | 默认根地址已进入统一界面；实际论文打开/刷新恢复、保存成果重开及兼容入口核对通过。三栏折叠/调宽/窄屏使用阶段6证据；见STAGE7_FINAL_RELEASE.md。 |'
        elif line.startswith('| A11 '):
            lines[index] = '| A11 比较、批判、研究依据 | 真实已验（固定案例范围） | v26批判完整成功，7条判断均有独立引用，真实条件与质量取舍明确，三种方法分别回应；v16直接比较已验，真实单子问题研究已发布，组合执行路径保持。原部分/失败不改写，离线回放不计新质量。见STAGE4_ACCEPTANCE.md；未宣称任意论文和无限规模研究正确。 |'
        elif line.startswith('| A19 '):
            lines[index] = '| A19 契约及文档边界 | 真实已验 | 最终7完整Schema样例通过、5错误样例拒绝，跨材料及请求归属404、重复GET不改任务；文档和默认入口同步。stage7-final-schema-v26.json、stage7-final-read-v26.json及Java既有48项记录。 |'
        elif line.startswith('| A14 '):
            lines[index] = line.replace('不等于阶段6完成', '验证范围以STAGE6_ACCEPTANCE.md为准')
    return '\n'.join(lines) + '\n'

edit('docs/STAGE7_ACCEPTANCE.md', acceptance)
edit('docs/REFACTOR_DEVELOPMENT_STAGES.md', lambda text: text.replace(
    '状态：阶段 0–3、5、6 已验收，阶段 4、7 尚未整体验收；完整重构尚未完成。',
    '状态：阶段0–7已按用户当前设计范围验收；统一默认入口已切换。').replace(
    '阶段4内容确认和阶段7默认入口切换仍待完成；已有本人体验反馈保留，不再要求完整新手观察。',
    '阶段4固定真实案例与阶段7默认入口已完成，见STAGE4_ACCEPTANCE.md及STAGE7_FINAL_RELEASE.md；已有本人体验反馈保留，不要求追加完整新手观察。'))
edit('docs/REFACTOR_BATCH_HANDOFF.md', lambda text: '\n'.join(
    '> 2026-10-10当前交接：阶段0–7按当前设计范围验收，统一根地址已启用。用户免验独立浏览器恢复及完整新手观察；前端303项、Python相关262项、Java既有48项及类型/构建通过。v26真实批判完整成功，12历史任务11收据保持。本轮3例各提交一次、累计40例，必要复测已统一授权。详见STAGE4_ACCEPTANCE、STAGE7_ACCEPTANCE和STAGE7_FINAL_RELEASE，下文为历史批次。'
    if line.startswith('> 2026-10-10当前交接：') else line for line in text.splitlines()) + '\n')
edit('docs/STAGE4_EXECUTION_PLAN.md', lambda text: text.replace(
    '状态：开发中，未验收。阶段 0–3 已验收，完整目标仍包含阶段 4–7。',
    '状态：按当前设计边界验收通过，见STAGE4_ACCEPTANCE.md。下面保留历史批次。').replace(
    text.splitlines()[2],
    '当前状态（2026-10-10）：v26真实批判完整成功，7条判断均通过；阶段4验收通过。用户统一授权后，本轮3例各一次，累计40例。最终262项相关回归通过，12旧任务11收据保持。下文为历史执行记录，不用于自动重发。'))
release = ROOT / 'docs/STAGE7_RELEASE_PLAN.md'
release.write_text('''# 阶段7发布记录

2026-10-10：已完成。阶段0–7按当前范围验收，统一任务界面默认从http://localhost:5173/进入。具体证据、数据保持和限制见[正式入口验收](STAGE7_FINAL_RELEASE.md)及[验收台账](STAGE7_ACCEPTANCE.md)。

用户已统一授权必要复测，既定公开论文及目的地见MODEL_VALIDATION_AUTHORIZATION.md；本轮v24、v25、v26各提交一次，累计40例。v26完整批判通过，原部分和失败记录保持。不再逐例索要同范围授权，也不无目的追加模型生成。

默认入口补丁已经应用，?unified=0旧入口及/share/优先路由已实际核验。反向补丁检查通过；需要回退代码时先核对当前差异，再反向应用stage2-evidence/stage7-default-entry.patch并重新构建。入口回退不恢复或覆盖数据库。

完整新手流程和独立Edge恢复按用户要求免验，不计实测通过。后续改进以真实使用问题驱动，不再作为当前交付的待办。
''', encoding='utf-8')

def guide(text):
    start = text.index('## 使用')
    end = text.index('## 正式切换与回退')
    body = text[start:end].replace('http://localhost:5173/?unified=1', 'http://localhost:5173/')
    return '''# 统一学术助手使用与运行说明

更新：2026-10-10。阶段0–7已按当前范围验收，统一界面已成为默认入口。详见[验收台账](STAGE7_ACCEPTANCE.md)和[正式入口验收](STAGE7_FINAL_RELEASE.md)。本指南介绍当前操作，历史失败和修复保留在各批次报告中。

''' + body + '''## 回退与恢复

默认根地址和?unified=1均进入统一界面，?unified=0保留旧界面回退，/share/路径仍走原共享页面。刷新恢复当前任务、论文和阅读位置；已保存成果保留，可从左侧或“打开成果”再次进入，中栏成果选中状态本轮刷新会回到论文。

入口回退不回滚或覆盖任务数据。本次不提供旧研究项目导入，不要求全量迁移旧资料；已有缓存兼容和无ID文档修复只用于必要读取。

## 当前范围和限制

真实批判、两论文比较、代表性单子问题研究及学习/阅读/整理链路按各阶段固定案例验证。新模型回答仍可能保留部分结果；原文存在和数字校验不等于通用语义证明，重要公式与机制结合原图核对。历史部分结果不会因代码修复自动改写。

当前没有OCR链路或整篇多页图文导出。成果能唯一关联一篇论文的一页时，可以查看原图或下载正文与原图的单文件HTML；Markdown含正文和折叠来源，不嵌入公式原图。原式定位区域可能包含邻近文字，旧缓存不会自动获得新坐标。

完整新手参与者流程和独立Edge恢复已按用户要求免验，不计通过。本轮v26批判7条判断完整成功；自动验证为前端303项、Python相关262项、Java既有48项，当前类型与生产构建通过。模型复测统一授权范围见MODEL_VALIDATION_AUTHORIZATION.md。
'''

edit('docs/UNIFIED_TASK_GUIDE.md', guide)
print('Updated current release documents; historical evidence retained.')
