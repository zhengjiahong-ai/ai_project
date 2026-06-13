import React from 'react';

import {
  BACKGROUND_DEPTH_OPTIONS,
  BACKGROUND_GOAL_OPTIONS,
  KNOWLEDGE_LEVEL_OPTIONS,
  normalizeKnowledgeLevel,
  normalizeReaderProfile,
} from './backgroundKnowledgePanelModel.js';

const BackgroundReaderProfileEditor = ({ value, onChange, compact = false }) => {
  const profile = normalizeReaderProfile(value);

  const handleFieldChange = (field, nextValue) => {
    onChange?.({
      ...profile,
      [field]: nextValue,
    });
  };

  const baseInputClass =
    'theme-card-soft theme-text-primary rounded-lg border border-transparent px-3 py-2 text-sm outline-none transition focus:border-pixiu/40';

  return (
    <div className={`grid gap-3 text-left ${compact ? 'xl:grid-cols-2' : 'lg:grid-cols-2'}`}>
      <label className="flex flex-col gap-2">
        <span className="theme-text-secondary text-xs font-medium">当前熟悉程度</span>
        <select
          value={normalizeKnowledgeLevel(profile.selfAssessedFamiliarity)}
          onChange={(event) =>
            handleFieldChange('selfAssessedFamiliarity', normalizeKnowledgeLevel(event.target.value))
          }
          className={baseInputClass}
        >
          {KNOWLEDGE_LEVEL_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-2">
        <span className="theme-text-secondary text-xs font-medium">希望补到多深</span>
        <select
          value={profile.preferredDepth}
          onChange={(event) => handleFieldChange('preferredDepth', event.target.value)}
          className={baseInputClass}
        >
          {BACKGROUND_DEPTH_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      <label className={`${compact ? 'xl:col-span-2' : 'lg:col-span-2'} flex flex-col gap-2`}>
        <span className="theme-text-secondary text-xs font-medium">这次补课目标</span>
        <input
          value={profile.learningGoal}
          onChange={(event) => handleFieldChange('learningGoal', event.target.value)}
          placeholder={BACKGROUND_GOAL_OPTIONS[0]}
          className={baseInputClass}
        />
      </label>

      <label className="flex flex-col gap-2">
        <span className="theme-text-secondary text-xs font-medium">我已经会</span>
        <input
          value={profile.knownConcepts.join('、')}
          onChange={(event) => handleFieldChange('knownConcepts', event.target.value)}
          placeholder="例如：Transformer、对比学习"
          className={baseInputClass}
        />
      </label>

      <label className="flex flex-col gap-2">
        <span className="theme-text-secondary text-xs font-medium">我现在卡住</span>
        <input
          value={profile.confusingConcepts.join('、')}
          onChange={(event) => handleFieldChange('confusingConcepts', event.target.value)}
          placeholder="例如：损失函数、图检索"
          className={baseInputClass}
        />
      </label>
    </div>
  );
};

export default BackgroundReaderProfileEditor;
