// Real shared Axios client against local Java. This is an API check, not browser proof.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { createApiClient, createApiService } from '../src/services/api.ts';

const filename = 'D:/3DGS/paper/LightGaussian/2311.17245v6.pdf';
const bytes = await readFile(filename);
const expected = createHash('sha256').update(bytes).digest('hex') + '.pdf';
const client = createApiClient('http://127.0.0.1:8081/api');
const service = createApiService(client);
const response = await service.uploadTaskMaterial(new File([bytes], '2311.17245v6.pdf', { type: 'application/pdf' }));
assert.equal(response.status, 'success');
assert.equal(response.pdfId, expected);
const task = await client.get('/task-workspaces/task%3Af8b18af5-9681-4bda-ad15-30fd2f3dbafe');
assert.ok(task.paperIds.includes(expected));
assert.equal(task.messages.length, 0);
const downloaded = await client.get(`/task-workspaces/${encodeURIComponent(task.id)}/materials/${expected}/file`, { responseType: 'arraybuffer', timeout: 20000 });
assert.equal(createHash('sha256').update(downloaded).digest('hex') + '.pdf', expected);
const receipt = { method: 'Actual shared Axios upload API followed by byte-for-byte server download',
  fileBytes: bytes.length, pdfId: expected, response: Object.fromEntries(
    ['status', 'pdfId', 'processingStatus', 'questionReady', 'aiAnalysisStatus'].map(key => [key, response[key]])), checks: { multipartAccepted: true, exactServerFileHash: true,
    existingTaskMembershipPreserved: true, noMessagesGenerated: true }, modelRequestsSubmitted: 0,
  limitation: 'The repaired browser file chooser flow remains unverified.' };
await writeFile(new URL('../../docs/stage2-evidence/stage6-upload-api-runtime.json', import.meta.url), JSON.stringify(receipt, null, 2));
console.log(JSON.stringify({ pdfId: expected, checks: receipt.checks, modelRequestsSubmitted: 0 }));
