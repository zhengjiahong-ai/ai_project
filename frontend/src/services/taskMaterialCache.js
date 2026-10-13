import { resolveStoredPdfRecord } from './workspaceSession';

/** Restore missing local caches from the same task's authoritative file and analysis. */
export async function loadTaskMaterial(db, api, taskId, paperId) {
  const [pdf, analysis, highlights] = await Promise.all([
    db.get('pdfStore', paperId), db.get('deconstructStore', paperId), db.get('highlightStore', paperId),
  ]);
  let record = resolveStoredPdfRecord(pdf);
  let deconstruct = analysis;
  let cacheWarning = '';
  const copyKey = `materialServerCopy:${paperId}`;
  if (!record || !deconstruct) {
    if (!taskId) throw new Error('请先选择论文所属任务');
    // Processing is available before extraction has produced an analysis record.
    // A status outage must not hide an already readable PDF.
    const [blob, outcome] = await Promise.all([
      record ? Promise.resolve(record.blob) : api.getMaterialFile(taskId, paperId),
      deconstruct ? Promise.resolve({ value: deconstruct }) :
        Promise.resolve().then(() => api.getMaterialProcessing
          ? api.getMaterialProcessing(taskId, paperId) : api.getMaterialAnalysis(taskId, paperId))
          .then(value => ({ value }), error => ({ error })),
    ]);
    if (!(blob instanceof Blob) || (!outcome.error && outcome.value?.pdfId !== paperId)) throw new Error('返回的论文文件或解析标识不匹配');
    if ([401, 403].includes(outcome.error?.response?.status)) throw outcome.error;
    record = { blob, name: record?.name || null };
    deconstruct = outcome.value || null;
    if (outcome.error) cacheWarning = '原文可阅读，正文状态暂不可获取；请稍后重新打开。';
    try {
      const transaction = db.transaction(['pdfStore', 'deconstructStore', 'metaStore'], 'readwrite');
      await Promise.all([
        transaction.objectStore('pdfStore').put(blob, paperId),
        ...(deconstruct ? [transaction.objectStore('deconstructStore').put(deconstruct, paperId)] : []),
        transaction.objectStore('metaStore').put(true, copyKey),
      ]);
      await transaction.done;
    } catch {
      cacheWarning = [cacheWarning, '原文已从服务端读取，但本地缓存保存失败；重新打开时需要连接服务。'].filter(Boolean).join(' ');
    }
  } else if (taskId && api.importMaterialCache && !await db.get('metaStore', copyKey)) {
    const library = await db.get('libraryStore', paperId);
    const filename = record.name || library?.filename;
    if (filename) {
      try {
        // Legacy browser names may differ from the original server filename.
        // The server still checks ownership and the actual PDF bytes on import.
        const materials = api.listMaterials ? await api.listMaterials(taskId) : [];
        const material = materials.find(item => item.id === paperId);
        if (material?.fileAvailable) {
          const [blob, result] = await Promise.all([api.getMaterialFile(taskId, paperId), api.getMaterialAnalysis(taskId, paperId)]);
          if (!(blob instanceof Blob) || result?.pdfId !== paperId) throw new Error('返回的论文文件或解析标识不匹配');
          const transaction = db.transaction(['pdfStore', 'deconstructStore', 'metaStore'], 'readwrite');
          await Promise.all([
            transaction.objectStore('metaStore').put({ pdf, analysis }, `materialLegacyBackup:${paperId}`),
            transaction.objectStore('pdfStore').put(blob, paperId),
            transaction.objectStore('deconstructStore').put(result, paperId),
            transaction.objectStore('metaStore').put(true, copyKey),
          ]);
          await transaction.done;
          record = { blob, name: material.filename };
          deconstruct = result;
        } else {
          await api.importMaterialCache(taskId, paperId, record.blob, material?.filename || filename, deconstruct);
          await db.put('metaStore', true, copyKey);
        }
      } catch (error) { cacheWarning = error.response?.data?.message || '本地论文仍可阅读，服务端备份未完成，请稍后重新打开重试。'; }
    }
  }
  return { record, deconstruct, highlights: Array.isArray(highlights) ? highlights : [], cacheWarning };
}
