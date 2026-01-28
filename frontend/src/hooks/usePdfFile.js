import { useState, useCallback } from 'react';

/**
 * PDF 文件管理 Hook
 * 用于管理 PDF 文件的上传、预览和清理
 */
export const usePdfFile = () => {
  const [pdfFile, setPdfFile] = useState(null);
  const [pdfFileName, setPdfFileName] = useState(null);
  const [pdfBlobUrl, setPdfBlobUrl] = useState(null);

  // 上传并预览 PDF
  const uploadPdf = useCallback((file) => {
    if (file && file.type === "application/pdf") {
      // 清理之前的 blob URL
      if (pdfBlobUrl) {
        URL.revokeObjectURL(pdfBlobUrl);
      }

      // 创建新的 blob URL
      const blobUrl = URL.createObjectURL(file);
      setPdfBlobUrl(blobUrl);
      setPdfFile(blobUrl);
      setPdfFileName(file.name);
      return { success: true, blobUrl, fileName: file.name };
    }
    return { success: false, error: '请上传有效的 PDF 文件' };
  }, [pdfBlobUrl]);

  // 清理 PDF（组件卸载时调用）
  const cleanup = useCallback(() => {
    if (pdfBlobUrl) {
      URL.revokeObjectURL(pdfBlobUrl);
      setPdfBlobUrl(null);
      setPdfFile(null);
      setPdfFileName(null);
    }
  }, [pdfBlobUrl]);

  return {
    pdfFile,
    pdfFileName,
    uploadPdf,
    cleanup,
  };
};
