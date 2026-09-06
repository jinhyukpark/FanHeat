from fanheat_ai.artist_writing import ArtistWritingRequest, Writing, write_artist


class StubLLM:
    def generate_json(self, messages, model):
        assert 'untrusted' in messages[0]['content']
        return Writing(entries=[
            {'text':'2021년 데뷔했다.', 'year':'2021', 'source_url':'https://official.test', 'quote':'IVE debuted in 2021 with ELEVEN.'},
            {'text':'상을 받았다.', 'year':'2022', 'source_url':'https://official.test', 'quote':'IVE debuted in 2021 with ELEVEN.'},
            {'text':'거짓 출처', 'year':'2021', 'source_url':'https://other.test', 'quote':'IVE debuted in 2021 with ELEVEN.'},
            {'text':'거짓 인용', 'year':'2021', 'source_url':'https://official.test', 'quote':'IVE won all awards in 2021.'},
        ])


def test_history_rejects_unknown_sources_fabricated_quotes_and_years():
    request=ArtistWritingRequest(artist_name='IVE',scope='history',sources=[{'url':'https://official.test','text':'IVE debuted in 2021 with ELEVEN.'}])
    result=write_artist(request,StubLLM())
    assert len(result['entries']) == 1
    assert result['rejected'] == 3
    assert result['review_required'] is True
