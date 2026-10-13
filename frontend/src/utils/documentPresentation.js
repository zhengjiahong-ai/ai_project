const genericTitle = /^(?:对话成果|对话笔记|批判阅读|批判报告|论文比较|比较结果|研究报告|学习记录|翻译成果|成果|笔记)(?:\s*\d+)?$/u;
const labels = { critique: '批判阅读', compare: '论文比较', research: '研究方案', translation: '译文', background: '基础概念', compose: '综合分析', note: '笔记', artifact: '阅读成果' };

export function documentKind(item, task) {
  if (task?.notes?.includes(item)) return 'note';
  const stored = item.type || item.kind || item.capability;
  const aliases = { 'translation-page': 'translation', 'research-report': 'research', comparison: 'compare', insight: 'artifact' };
  if (stored && !['artifact', 'insight'].includes(stored)) return aliases[stored] || stored;
  if (item.sourceResearchId) return 'research';
  if (Number.isInteger(item.pageIndex) && /译文|翻译/u.test(item.title || '')) return 'translation';
  return task?.messages?.find(message => message.artifactId === (item.id || item.artifactId))?.capability || 'artifact';
}

export function paperShortName(paper, fallback = '') {
  return (paper?.title || paper?.filename || fallback).replace(/\.pdf$/iu, '').split(/[:：]/u)[0].trim();
}

export function questionTopic(question) {
  const topic = String(question || '').replace(/@\{[^}]+\}/gu, '').replace(/^\s*\/\S+\s*/u, '').trim()
    .replace(/^(?:(?:请你|帮我|麻烦你|能否|请)\s*)+/u, '')
    .replace(/^(?:仅依据|只依据|只根据|仅根据)[^:：。]*[:：。]\s*/u, '')
    .replace(/^对.+?(?:作|做|进行)?批判阅读[:：]\s*/u, '').replace(/^研究一个问题[:：]\s*/u, '')
    .split(/[\n。；;？?]/u).map(line => line.trim()).find(line => line && !/^(?:不用|不要)(?:外部|联网|搜索)/u.test(line))
    ?.split(/[,，](?:请|给|只|不|区分|输出|控制|字数)/u)[0].replace(/[！!。]+$/u, '').trim() || '';
  if (/最影响复现和使用决策/u.test(topic)) return '复现与使用决策的关键判断';
  if (/画质几乎不变.*(?:条件|成立)/u.test(topic)) return '画质保持的适用条件';
  return topic.length <= 96 ? topic : '';
}

/** A presentation fallback only. Never mutate legacy records or infer a scientific conclusion. */
export function documentDisplayTitle(item, task, papers = []) {
  const title = String(item.title || '').trim();
  if (title && (!genericTitle.test(title) || item.titleOrigin === 'user')) return title;
  const kind = documentKind(item, task);
  const messageIndex = task?.messages?.findIndex(message => message.id === item.sourceMessageId
    || message.artifactId === (item.id || item.artifactId));
  const original = messageIndex >= 0 ? task.messages.slice(0, messageIndex + 1).findLast(message => message.role === 'user')?.content : '';
  const research = task?.researchRuns?.find(run => run.researchId === item.sourceResearchId);
  const topic = questionTopic(item.critique?.question?.original || item.question || research?.question || original);
  const paperId = item.critique?.scope?.targetPaperIds?.[0] || item.paperIds?.[0] || item.source?.sourcePdfId;
  const paper = papers.find(entry => entry.id === paperId);
  const name = paperShortName(paper);
  if (topic) return name && !topic.includes(name) && kind !== 'compare' ? `${name}：${topic}` : topic;
  if (kind === 'translation' && Number.isInteger(item.pageIndex)) return `${name ? `${name} · ` : ''}第${item.pageIndex + 1}页译文`;
  return name ? `${name} · ${labels[kind] || '阅读成果'}` : title || labels[kind] || '未命名成果';
}
