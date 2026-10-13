import React from 'react';
import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { LearningRecordContent } from './LearningHistory';

it('shows the retained answers and Markdown feedback without treating an ended activity as mastery',()=>{
  const activity={status:'finished',mode:'quiz',concepts:[{id:'one',question:'为什么有偏差？',status:'pending'},
    {id:'two',question:'如何验证？',status:'skipped'}, {id:'three',question:'何时成立？',status:'demonstrated'}],
    turns:[{conceptId:'one',action:'answer',text:'这是我的真实回答',feedback:JSON.stringify({feedback:'**仍需解释** 采样误差',suggestions:['补充证据'],requestId:'internal-id'})}]};
  render(<LearningRecordContent activity={activity} papers={[]}/>);
  expect(screen.getByText('自测 · 已结束')).toBeInTheDocument();
  expect(screen.getByText('未核验')).toBeInTheDocument();
  expect(screen.getByText('已跳过')).toBeInTheDocument();
  expect(screen.getByText('已核验')).toBeInTheDocument();
  expect(screen.queryByText('已掌握')).not.toBeInTheDocument();
  expect(screen.getByText('这是我的真实回答')).toBeInTheDocument();
  expect(screen.getByText('仍需解释').tagName).toBe('STRONG');
  expect(screen.getByText(/补充证据/)).toBeInTheDocument();
  expect(screen.getByRole('article')).not.toHaveTextContent('requestId');
  expect(screen.getByRole('article')).not.toHaveTextContent('{"feedback"');
});

it('keeps paused imported records distinct and reads legacy question/answer fields',()=>{
  render(<LearningRecordContent activity={{imported:true,status:'paused',turns:[{question:'旧记录问题',answer:'旧记录回答',feedback:{text:'旧记录反馈'},masteryLevel:'需加强'}]}}/>);
  expect(screen.getByText('精读 · 已暂停')).toBeInTheDocument();
  expect(screen.getByText('旧记录问题')).toBeInTheDocument();
  expect(screen.getByText('旧记录回答')).toBeInTheDocument();
  expect(screen.getByText('旧记录反馈')).toBeInTheDocument();
  expect(screen.getByText('本题反馈：需加强')).toBeInTheDocument();
  expect(screen.queryByText('已掌握')).not.toBeInTheDocument();
});
