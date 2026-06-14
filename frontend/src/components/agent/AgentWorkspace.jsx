import React, { useMemo, useState } from 'react';
import {
  ArrowUp,
  CheckCircle2,
  Clock3,
  FilePlus2,
  FileText,
  Layers3,
  ListChecks,
  MessageSquareText,
  PlayCircle,
  Search,
  Sparkles,
} from 'lucide-react';

import {
  agentEvidenceItems,
  agentPapers,
  agentPlanSteps,
  agentQuickTasks,
  agentToolCalls,
} from './agentMockData.js';

const statusClassName = {
  done: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20',
  running: 'bg-pixiu/10 text-pixiu border-pixiu/20',
  waiting: 'theme-card-soft theme-text-muted',
};

const getStepIcon = (status) => {
  if (status === 'done') {
    return <CheckCircle2 size={15} />;
  }
  if (status === 'running') {
    return <PlayCircle size={15} />;
  }
  return <Clock3 size={15} />;
};

const AgentProjectSidebar = () => (
  <aside className="theme-panel theme-border flex min-w-0 flex-col overflow-hidden border-r">
    <div className="theme-border flex h-14 shrink-0 items-center justify-between border-b px-4">
      <div className="min-w-0">
        <h2 className="theme-text-primary text-sm font-bold">研究工作区</h2>
        <p className="theme-text-muted truncate text-[11px]">多论文协作原型</p>
      </div>
      <button
        type="button"
        className="theme-button-secondary flex h-8 w-8 items-center justify-center rounded-md"
        title="添加论文"
      >
        <FilePlus2 size={15} />
      </button>
    </div>

    <div className="flex-1 overflow-y-auto p-4">
      <section className="theme-card rounded-xl p-4">
        <div className="text-[11px] font-bold uppercase tracking-wide text-pixiu">Research Topic</div>
        <h3 className="theme-text-primary mt-2 text-sm font-bold leading-5">
          大模型辅助学术阅读与跨论文分析
        </h3>
        <div className="mt-3 flex flex-wrap gap-2">
          <span className="rounded-full bg-pixiu/10 px-2 py-1 text-[10px] font-semibold text-pixiu">
            3 篇论文
          </span>
          <span className="rounded-full bg-emerald-500/10 px-2 py-1 text-[10px] font-semibold text-emerald-600">
            2 篇已索引
          </span>
        </div>
      </section>

      <section className="mt-5">
        <div className="theme-text-muted mb-2 flex items-center justify-between text-xs font-bold">
          <span>Papers</span>
          <span>解析 / 索引</span>
        </div>
        <div className="space-y-2">
          {agentPapers.map((paper, index) => (
            <article
              key={paper.id}
              className={`theme-border rounded-xl border p-3 transition ${
                index === 0 ? 'bg-pixiu/10' : 'theme-panel hover:border-pixiu/40'
              }`}
            >
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-8 shrink-0 items-center justify-center rounded-lg bg-pixiu/10 text-pixiu">
                  <FileText size={15} />
                </div>
                <div className="min-w-0 flex-1">
                  <h4 className="theme-text-primary line-clamp-2 text-xs font-bold leading-5">{paper.title}</h4>
                  <div className="theme-text-muted mt-1 flex items-center gap-2 text-[10px]">
                    <span>{paper.year}</span>
                    <span>{paper.status}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {paper.tags.map((tag) => (
                      <span key={tag} className="theme-card-soft rounded px-1.5 py-0.5 text-[10px] theme-text-secondary">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="mt-5">
        <div className="theme-text-muted mb-2 text-xs font-bold">最近任务</div>
        <div className="space-y-2">
          {['方法路线对比', '核心创新点归纳', '实验指标整理'].map((task) => (
            <button
              key={task}
              type="button"
              className="theme-border theme-panel w-full rounded-lg border px-3 py-2 text-left text-xs font-semibold transition hover:border-pixiu/40 hover:text-pixiu"
            >
              {task}
            </button>
          ))}
        </div>
      </section>
    </div>
  </aside>
);

const AgentPlanBlock = () => (
  <div className="theme-card-soft rounded-xl p-3">
    <div className="mb-3 flex items-center gap-2 text-xs font-bold theme-text-primary">
      <ListChecks size={15} className="text-pixiu" />
      执行计划
    </div>
    <div className="space-y-2">
      {agentPlanSteps.map((step, index) => (
        <div
          key={step.id}
          className={`theme-border grid grid-cols-[28px_1fr_auto] gap-3 rounded-lg border p-3 ${
            step.status === 'running' ? 'bg-pixiu/5' : 'theme-panel'
          }`}
        >
          <div className={`flex h-7 w-7 items-center justify-center rounded-full border text-xs ${statusClassName[step.status]}`}>
            {getStepIcon(step.status)}
          </div>
          <div className="min-w-0">
            <div className="theme-text-primary text-xs font-bold">
              {index + 1}. {step.label}
            </div>
            <div className="theme-text-secondary mt-1 text-[11px] leading-5">{step.detail}</div>
          </div>
          <span className={`self-start rounded-full border px-2 py-0.5 text-[10px] font-semibold ${statusClassName[step.status]}`}>
            {step.status === 'done' ? '完成' : step.status === 'running' ? '进行中' : '等待'}
          </span>
        </div>
      ))}
    </div>
  </div>
);

const AgentToolTrace = () => (
  <div className="theme-card-soft rounded-xl p-3">
    <div className="mb-3 flex items-center gap-2 text-xs font-bold theme-text-primary">
      <Search size={15} className="text-pixiu" />
      工具调用
    </div>
    <div className="space-y-2">
      {agentToolCalls.slice(0, 3).map((call) => (
        <div key={call.id} className="theme-border theme-panel rounded-lg border p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="theme-text-primary text-xs font-bold">{call.name}</span>
            <span className="rounded-full bg-pixiu/10 px-2 py-0.5 text-[10px] font-semibold text-pixiu">
              {call.status}
            </span>
          </div>
          <div className="theme-text-secondary mt-2 grid gap-1 text-[11px] leading-5">
            <span>目标：{call.target}</span>
            <span>结果：{call.result}</span>
          </div>
        </div>
      ))}
    </div>
  </div>
);

const AgentChatWorkspace = () => {
  const [inputValue, setInputValue] = useState('');
  const [extraTasks, setExtraTasks] = useState([]);

  const currentTask = useMemo(
    () => extraTasks[extraTasks.length - 1] || '比较这些论文在研究问题、方法设计、实验指标和局限性上的差异。',
    [extraTasks],
  );

  const handleSend = () => {
    const text = inputValue.trim();
    if (!text) {
      return;
    }
    setExtraTasks((items) => [...items, text]);
    setInputValue('');
  };

  return (
    <section className="theme-panel flex min-w-0 flex-col overflow-hidden">
      <div className="theme-border flex h-14 shrink-0 items-center justify-between border-b px-4">
        <div className="min-w-0">
          <h2 className="theme-text-primary truncate text-sm font-bold">Agent 研究任务</h2>
          <p className="theme-text-muted truncate text-[11px]">底部输入任务，上方展示执行过程和回答</p>
        </div>
        <span className="rounded-full bg-pixiu/10 px-3 py-1 text-[11px] font-semibold text-pixiu">
          前端框架原型
        </span>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto bg-gradient-to-b from-white to-slate-50/70 p-5 dark:from-slate-900 dark:to-slate-950">
        <div className="flex justify-end">
          <div className="max-w-[78%] rounded-2xl rounded-br-md bg-pixiu px-4 py-3 text-sm leading-7 text-white shadow-sm">
            {currentTask}
          </div>
        </div>

        <div className="theme-card max-w-4xl rounded-2xl p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-pixiu text-white">
                <Sparkles size={16} />
              </div>
              <div>
                <div className="theme-text-primary text-sm font-bold">Pixiu Research Agent</div>
                <div className="theme-text-muted text-[11px]">正在整理可解释执行过程</div>
              </div>
            </div>
            <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-600">
              可追溯
            </span>
          </div>

          <div className="theme-card-soft mt-4 rounded-xl p-3">
            <div className="mb-2 flex items-center gap-2 text-xs font-bold theme-text-primary">
              <MessageSquareText size={15} className="text-pixiu" />
              任务理解
            </div>
            <p className="theme-text-secondary text-sm leading-7">
              我会先确认参与分析的论文范围，再检索每篇论文的关键章节，最后从研究问题、方法设计、创新点和局限性几个维度生成跨论文对比。
            </p>
          </div>

          <div className="mt-3 grid gap-3 xl:grid-cols-2">
            <AgentPlanBlock />
            <AgentToolTrace />
          </div>

          <div className="theme-card-soft mt-3 rounded-xl p-3">
            <div className="mb-2 flex items-center gap-2 text-xs font-bold theme-text-primary">
              <Layers3 size={15} className="text-pixiu" />
              阶段性结果
            </div>
            <div className="grid gap-2 md:grid-cols-3">
              {[
                ['共同问题', '如何让大模型在知识密集型任务中产生更可靠的回答。'],
                ['方法差异', 'RAG 强调外部知识，Self-RAG 强调生成后的自我批判，Toolformer 强调工具选择。'],
                ['证据覆盖', '当前已整理方法、实验和结论相关证据片段。'],
              ].map(([title, content]) => (
                <div key={title} className="theme-border theme-panel rounded-lg border p-3">
                  <div className="theme-text-primary text-xs font-bold">{title}</div>
                  <p className="theme-text-secondary mt-1 text-[11px] leading-5">{content}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-3 overflow-hidden rounded-xl border theme-border">
            <div className="theme-card-soft border-b px-3 py-2 text-xs font-bold theme-border theme-text-primary">
              研究结论草稿
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] text-left text-xs">
                <thead className="theme-card-soft theme-text-muted">
                  <tr>
                    <th className="px-3 py-2 font-bold">论文</th>
                    <th className="px-3 py-2 font-bold">关注点</th>
                    <th className="px-3 py-2 font-bold">主要方法</th>
                    <th className="px-3 py-2 font-bold">可追溯证据</th>
                  </tr>
                </thead>
                <tbody className="theme-panel theme-text-secondary">
                  <tr className="border-t theme-border">
                    <td className="px-3 py-2 font-semibold text-pixiu">RAG</td>
                    <td className="px-3 py-2">外部知识增强生成</td>
                    <td className="px-3 py-2">检索器 + 生成器</td>
                    <td className="px-3 py-2">Methods p.3</td>
                  </tr>
                  <tr className="border-t theme-border">
                    <td className="px-3 py-2 font-semibold text-pixiu">Self-RAG</td>
                    <td className="px-3 py-2">减少无证据回答</td>
                    <td className="px-3 py-2">检索、生成、自我批判闭环</td>
                    <td className="px-3 py-2">Approach p.5</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {extraTasks.slice(0, -1).map((task) => (
          <div key={task} className="flex justify-end opacity-70">
            <div className="max-w-[70%] rounded-2xl bg-pixiu/80 px-4 py-2 text-xs leading-6 text-white">
              {task}
            </div>
          </div>
        ))}
      </div>

      <div className="theme-panel-muted theme-border shrink-0 border-t px-5 py-4">
        <div className="mb-2 flex flex-wrap gap-2">
          {agentQuickTasks.map((task) => (
            <button
              key={task}
              type="button"
              onClick={() => setInputValue(`请帮我做${task}，并给出可追溯证据。`)}
              className="theme-quick-tag rounded-full px-3 py-1 text-[11px] font-semibold transition"
            >
              {task}
            </button>
          ))}
        </div>
        <div className="theme-input grid grid-cols-[1fr_auto] gap-2 rounded-2xl p-2">
          <textarea
            rows={2}
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            className="min-h-[52px] resize-none bg-transparent px-2 py-1 text-sm leading-6 outline-none"
            placeholder="让 Agent 比较这些论文的研究问题、方法设计、实验指标和局限性"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!inputValue.trim()}
            className="self-end rounded-xl bg-pixiu p-2.5 text-white shadow-sm transition hover:bg-pixiu-dark disabled:cursor-not-allowed disabled:opacity-50"
            title="启动 Agent"
          >
            <ArrowUp size={18} />
          </button>
        </div>
      </div>
    </section>
  );
};

const AgentEvidencePanel = () => (
  <aside className="theme-panel theme-border flex min-w-0 flex-col overflow-hidden border-l">
    <div className="theme-border flex h-14 shrink-0 items-center justify-between border-b px-4">
      <div className="min-w-0">
        <h2 className="theme-text-primary text-sm font-bold">工具调用与证据链</h2>
        <p className="theme-text-muted truncate text-[11px]">展示 Agent 做了什么、依据在哪里</p>
      </div>
      <span className="rounded-full bg-emerald-500/10 px-2 py-1 text-[10px] font-semibold text-emerald-600">
        可追溯
      </span>
    </div>

    <div className="flex-1 overflow-y-auto p-4">
      <section>
        <div className="theme-text-muted mb-2 text-xs font-bold">当前工具</div>
        <div className="space-y-2">
          {agentToolCalls.map((call) => (
            <article key={call.id} className="theme-border theme-panel rounded-xl border p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="theme-text-primary text-xs font-bold">{call.name}</span>
                <span className="theme-card-soft rounded-full px-2 py-0.5 text-[10px] font-semibold theme-text-secondary">
                  {call.status}
                </span>
              </div>
              <div className="theme-text-secondary mt-2 text-[11px] leading-5">{call.result}</div>
            </article>
          ))}
        </div>
      </section>

      <section className="mt-5">
        <div className="theme-text-muted mb-2 text-xs font-bold">引用证据片段</div>
        <div className="space-y-3">
          {agentEvidenceItems.map((item) => (
            <article key={item.id} className="theme-border theme-panel rounded-xl border p-3">
              <h3 className="theme-text-primary line-clamp-2 text-xs font-bold leading-5">{item.paper}</h3>
              <div className="mt-1 text-[11px] font-semibold text-pixiu">{item.location}</div>
              <p className="theme-text-secondary mt-2 border-l-2 border-pixiu/30 pl-3 text-[11px] leading-5">
                {item.quote}
              </p>
              <div className="mt-3 flex gap-2">
                <button type="button" className="theme-quick-tag rounded px-2 py-1 text-[10px] font-bold">
                  查看原文
                </button>
                <button type="button" className="theme-quick-tag rounded px-2 py-1 text-[10px] font-bold">
                  加入报告
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  </aside>
);

const AgentWorkspace = () => (
  <div className="grid h-full min-h-0 grid-cols-[280px_minmax(0,1fr)_340px] overflow-hidden max-xl:grid-cols-[250px_minmax(0,1fr)_300px] max-lg:grid-cols-[minmax(0,1fr)]">
    <div className="min-h-0 max-lg:hidden">
      <AgentProjectSidebar />
    </div>
    <AgentChatWorkspace />
    <div className="min-h-0 max-lg:hidden">
      <AgentEvidencePanel />
    </div>
  </div>
);

export default AgentWorkspace;
