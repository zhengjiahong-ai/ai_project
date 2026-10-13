"""Verify both unapproved starts fail before any local or external request."""
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

runner = Path(__file__).with_name('verify_stage4_v12.py')
for case in ('critique', 'compare'):
    with (patch.object(sys, 'argv', [str(runner), case, 'start', 'v13']),
          patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')) as network):
        try:
            runpy.run_path(str(runner), run_name='__main__')
        except AssertionError as error:
            assert str(error) == 'Explicit new authorization required'
        else:
            raise AssertionError('Unapproved start was accepted')
        assert network.call_count == 0
print('Both v13 starts refused before network; requests=0, submissions=0')
