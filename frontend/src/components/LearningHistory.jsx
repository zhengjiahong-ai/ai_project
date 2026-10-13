import React from 'react';
import { ChevronRight } from 'lucide-react';
import MarkdownContent from './MarkdownContent';
import { questionTopic } from '../utils/documentPresentation';
import { searchExcerpt } from '../utils/navigationSearch';
import './TaskNavigationDetails.css';

const statusLabel = activity => ({ finished: '已结束', paused: '已暂停', running: '进行中', active: '进行中' }[activity.status]
  || (activity.imported ? '已保存' : '历史记录'));

// Some imported records kept structured feedback instead of plain Markdown.
// Display the retained text fields without exposing serialized storage records.
const feedbackMarkdown = value => {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try { return feedbackMarkdown(JSON.parse(trimmed)); } catch { /* Ordinary prose remains readable. */ }
    }
    return value;
  }
  if (Array.isArray(value)) return value.map(feedbackMarkdown).filter(Boolean).join('\n\n');
  if (!value || typeof value !== 'object') return '';
  const labels = { masteryLevel: '掌握反馈', suggestions: '建议', missingAspects: '待补充', coveredAspects: '已涉及' };
  return Object.entries(value).filter(([key]) => !['id', 'conceptId', 'requestId', 'status', 'verdict', 'confidence'].includes(key))
    .map(([key, content]) => {
      const text = feedbackMarkdown(content);
      return text ? (labels[key] ? `**${labels[key]}**：${text}` : text) : '';
    }).filter(Boolean).join('\n\n');
};

export const learningSearchText = (activity, papers = []) => {
  const paper = papers.find(item => item.id === (activity.pdfId || activity.primaryPaperId));
  return [activity.title, activity.goal, activity.finalSummary, paper?.title, paper?.filename,
    ...(activity.concepts || []).map(concept => [concept.question, concept.label].filter(Boolean).join(' ')),
    ...(activity.turns || []).map(turn => [turn.question, turn.text, turn.answer, feedbackMarkdown(turn.feedback), turn.hint].filter(Boolean).join(' ')),
  ].filter(Boolean).join(' ');
};
const feedbackLabels = { hint: '提示', remediate: '补课', ask: '追问反馈', skip: '跳过反馈' };

export default function LearningHistory({ activities = [], papers = [], onOpen, searchActive = false, searchQuery = '', selectedLearningId }) {
  if (!activities.length) return null;
  return <details key={searchActive ? `search:${searchQuery}` : 'browse'} open={searchActive || undefined} className="unified-learning-history task-learning-history">
    <summary className="unified-learning-history-toggle"><ChevronRight size={14} aria-hidden="true" />学习记录（{activities.length}）</summary>
    <div className="unified-learning-history-list">
      {activities.map((activity, index) => {
        const paperId = activity.pdfId || activity.primaryPaperId;
        const paper = papers.find(item => item.id === paperId);
        const title = paper?.title || paper?.filename || '论文';
        const shortTitle = title.split(/[:：]/u)[0].trim() || title;
        const mode = activity.mode === 'quiz' ? '自测' : '精读';
        const concepts = activity.concepts || [];
        const turns = activity.turns || [];
        const topic = questionTopic(activity.title || activity.goal || concepts[0]?.question);
        const recordTitle = topic && !topic.includes(shortTitle) ? `${shortTitle}：${topic}` : topic || shortTitle;
        if (onOpen) return <button type="button" className="unified-learning-record-toggle unified-learning-record-link" key={activity.activityId || activity.id || index}
          aria-current={selectedLearningId && selectedLearningId === (activity.activityId || activity.id) ? 'page' : undefined} aria-label={`${mode} · ${recordTitle} · ${statusLabel(activity)}`} title={`${mode} · ${recordTitle} · ${statusLabel(activity)}`} onClick={() => onOpen(activity)}>
          <span className="unified-learning-record-mode">{mode}</span><span className="unified-learning-record-title">{recordTitle}{searchActive && <span className="workbench-search-excerpt">{searchExcerpt(learningSearchText(activity, papers), searchQuery)}</span>}</span><span className="unified-learning-record-status">{statusLabel(activity)}</span>
        </button>;
        return <details className="unified-learning-record" key={activity.activityId || activity.id || index}>
          <summary className="unified-learning-record-toggle">
            <ChevronRight size={13} aria-hidden="true" />
            <span className="unified-learning-record-mode">{mode}</span>
            <span className="unified-learning-record-title" title={title}>{shortTitle}</span>
            <span className="unified-learning-record-status">{statusLabel(activity)}</span>
          </summary>
          <div className="unified-learning-record-body">
            <p className="unified-learning-record-paper">{title}</p>
            {concepts.length ? concepts.map((concept, conceptIndex) => <section key={concept.id || conceptIndex}>
              <h3>问题{concepts.length > 1 ? ` ${conceptIndex + 1}` : ''}</h3>
              <p>{concept.question || concept.label || activity.goal || '已保存学习记录'}</p>
              {turns.filter(turn => concept.id && turn.conceptId === concept.id).map((turn, turnIndex) => <LearningTurn key={turnIndex} turn={turn} />)}
            </section>) : activity.goal && <p>{activity.goal}</p>}
            {turns.filter(turn => !concepts.some(concept => concept.id && concept.id === turn.conceptId)).map((turn, turnIndex) => <LearningTurn key={`other-${turnIndex}`} turn={turn} />)}
          </div>
        </details>;
      })}
    </div>
  </details>;
}

function LearningTurn({ turn }) {
  const answer = turn.answer || (['answer', 'ask'].includes(turn.action) ? turn.text : '');
  const feedback = feedbackMarkdown(turn.feedback);
  return <div className="unified-learning-record-turn">
    {turn.question && <><h3>问题</h3><MarkdownContent>{turn.question}</MarkdownContent></>}
    {answer && <><h3>{turn.action === 'ask' ? '你的追问' : '你的回答'}</h3><MarkdownContent>{answer}</MarkdownContent></>}
    {feedback && <><h3>{feedbackLabels[turn.action] || '反馈'}</h3><MarkdownContent>{feedback}</MarkdownContent></>}
    {turn.hint && <><h3>提示</h3><MarkdownContent>{turn.hint}</MarkdownContent></>}
    {turn.masteryLevel && <p className="theme-text-secondary">本题反馈：{turn.masteryLevel}</p>}
  </div>;
}

export function LearningRecordContent({ activity, papers = [] }) {
  if (!activity) return null;
  const paper = papers.find(item => item.id === (activity.pdfId || activity.primaryPaperId));
  const concepts = activity.concepts || [];
  const turns = activity.turns || [];
  return <article className="unified-learning-detail" aria-label="学习记录详情">
    <p className="theme-text-secondary">{activity.mode === 'quiz' ? '自测' : '精读'} · {statusLabel(activity)}</p>
    {activity.status === 'finished' && <p className="theme-text-muted text-sm">本次学习已结束；各题核验情况以保留记录为准。</p>}
    <p className="theme-text-secondary">{paper?.title || paper?.filename || '论文'}</p>
    {activity.goal && <MarkdownContent>{activity.goal}</MarkdownContent>}
    {concepts.map((concept, index) => <section key={concept.id || index}>
      <h3>问题{concepts.length > 1 ? ` ${index + 1}` : ''}</h3><MarkdownContent>{concept.question || concept.label}</MarkdownContent>
      <p className="unified-learning-detail-status">{{ demonstrated: '已核验', skipped: '已跳过', pending: '未核验' }[concept.status] || '未核验'}</p>
      {turns.filter(turn => concept.id && turn.conceptId === concept.id).map((turn, turnIndex) => <LearningTurn key={turnIndex} turn={turn} />)}
    </section>)}
    {turns.filter(turn => !concepts.some(concept => concept.id && concept.id === turn.conceptId)).map((turn, index) => <LearningTurn key={index} turn={turn} />)}
    {activity.finalSummary && <section><h3>学习总结</h3><MarkdownContent>{activity.finalSummary}</MarkdownContent></section>}
  </article>;
}
