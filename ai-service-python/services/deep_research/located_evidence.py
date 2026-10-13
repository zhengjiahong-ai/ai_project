"""Bind new local prose evidence to the physical pages of its frozen PDF."""
import subprocess
import requests
from services.deep_research.contracts import DeepResearchError
from services.deep_research.verification import make_evidence


def located_evidence_factory(repo, run_id, local):
    # LocalTaskRetriever owns the per-run PDF cache. Nothing is written back to
    # historical sources/reports, and evidence identity includes the new location.
    def create(source, quote, original, *, location, obligation_ids, conditions=None):
        from services.deep_research.quote_pages import resolve_quote_location
        record = repo.require_run(run_id)
        material = next((m for m in record.get('materials', [])
                         if m.get('materialId') == source.get('workId')), None)
        if material and source.get('accessLevel') == 'fulltext':
            # Verified table rows are a parser serialization, not literal PDF
            # prose. Keep their existing geometric locator only when the exact
            # persisted source packet proves this is such a row.
            from services.deep_research.table_evidence import visible_table_packet
            table_row = False
            for item in record.get('state', {}).get('sources', []):
                if (item.get('workId') != source.get('workId') or
                        item.get('contentHash') != source.get('contentHash') or
                        item.get('versionId') != source.get('versionId')):
                    continue
                packet = visible_table_packet(item.get('tableData'), original)
                if packet:
                    table_row = any(quote == f'Table row {n}: ' + ' | '.join([method, *values])
                                    for n, method, values in packet['rows'])
                if table_row:
                    break
            if not table_row:
                try:
                    _, pages = local.load_pages(source['workId'])
                except DeepResearchError as exc:
                    if exc.code in {'scope_revoked', 'source_changed', 'source_missing'}:
                        raise
                    # A transient file/parse failure must never endorse the old
                    # section page. Evidence text is still checked independently.
                    pages = []
                except (requests.RequestException, subprocess.TimeoutExpired):
                    pages = []
                location = resolve_quote_location(quote, pages, location)
        return make_evidence(source, quote, original, location=location,
                             obligation_ids=obligation_ids, conditions=conditions)
    return create
