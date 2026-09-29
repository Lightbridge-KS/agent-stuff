#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer==0.19.2", "PyYAML==6.0.3", "markdown-it-py==4.0.0", "jsonschema==4.25.1"]
# ///
"""Hermetic form/transport/archive contracts; ASK_QMD_LIVE=1 includes Quarto."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / 'plugins/experiment/skills/ask-form-qmd'
sys.path.insert(0, str(SKILL / 'scripts'))
import aq_document as doc
import aq_form as form
import aq_store as store
import aq_session as session
import aq_viewer as viewer

QUESTIONS = [
    {'id':'choice','type':'single_select','label':'Choice','required':True,'options':[{'value':'a','label':'A','recommended':True},{'value':'b','label':'B'}]},
    {'id':'multi','type':'multi_select','label':'Many','options':[{'value':'a','label':'A'}],'max':2},
    {'id':'scale','type':'scale','label':'Scale','min':0,'max':5,'step':.5},
    {'id':'number','type':'number','label':'Number','min':0,'step':5},
    {'id':'rank','type':'ranking','label':'Rank','options':[{'value':'a','label':'A'},{'value':'b','label':'B'}]},
    {'id':'text','type':'short_text','label':'Text','max_length':20},
    {'id':'long','type':'long_text','label':'Long'},
    {'id':'matrix','type':'matrix','label':'Matrix','required':True,'rows':[{'value':'r','label':'R'}],'columns':[{'value':'c','label':'C'}]},
    {'id':'review','type':'review','label':'Review','required':True,'items':[{'id':'item','label':'Item','recommended':'approve'}]},
]
BODY = {'answers':{'choice':'b','multi':['a','custom'],'scale':2.5,'number':10,'rank':['b','a'],'text':'ไทย','long':'Reasoning','matrix':{'r':'c'},'review':{'item':{'decision':'revise','comment':'Change it'}}},'other':['multi'],'notes':{'choice':'A note'},'comments':'Overall'}


def fixture(directory):
    bundle = directory / 'bundle'
    (bundle / 'rendered').mkdir(parents=True)
    (bundle / 'assets').mkdir()
    (bundle / 'source.qmd').write_text('---\ntitle: Fixture\n---\nContext')
    (bundle / 'form.json').write_text(json.dumps({'version':1,'title':'Fixture','questions':QUESTIONS,'context':'Context\n\n'+'\n\n'.join('AQANSWER_'+q['id'] for q in QUESTIONS)}))
    (bundle / 'rendered/index.html').write_text('<html><body>' + doc.SNAPSHOT + '</body></html>')
    manifest = {'producer':'ask-form-qmd','schema_version':1,'created':'2026-09-25','warnings':[]}
    _, result = form.validate_answers(BODY, QUESTIONS)
    result.update(status='submitted')
    result['meta'].update(ask_id=store.new_id('Fixture'), duration_s=1)
    return bundle, manifest, result


class ContractTests(unittest.TestCase):
    def test_every_type_and_metadata(self):
        for q in QUESTIONS:
            self.assertEqual(form.validate_question(q), [])
        errors, result = form.validate_answers(BODY, QUESTIONS)
        self.assertEqual(errors,{})
        self.assertEqual(result['answers']['rank'],['b','a'])
        self.assertEqual(result['meta']['diverged'],['choice','review'])
        self.assertEqual(result['meta']['notes'],{'choice':'A note'})

    def test_answers_reject_malformed_values_without_crashing(self):
        cases = [('number',float('nan')),('number',float('inf')),('number',True),('number',11),('multi',['a','a']),('rank',['a',{}]),('matrix',{}),('review',{}),('review',{'item':{'decision':[]}}),('text',' '*3),('choice','unknown')]
        for key,value in cases:
            with self.subTest(key=key,value=value):
                body=copy.deepcopy(BODY);body['answers'][key]=value
                self.assertIn(key,form.validate_answers(body,QUESTIONS)[0])
        for body in (None, [], {'answers':[]}, {'answers':{},'notes':{'unknown':'x'}}, {'answers':{},'other':[[]]}):
            self.assertTrue(form.validate_answers(body,QUESTIONS)[0])

    def test_spec_unknown_duplicate_nonfinite_and_unsatisfiable(self):
        for patch_value in ({'unexpected':True},{'min':float('nan')},{'recommended':3.2}):
            q={**QUESTIONS[2],**patch_value};self.assertTrue(form.validate_question(q))
        q=copy.deepcopy(QUESTIONS[0]);q['options'].append(q['options'][0]);self.assertTrue(form.validate_question(q))
        q=copy.deepcopy(QUESTIONS[1]);q.update(allow_other=False,min=9);self.assertTrue(form.validate_question(q))
        for changes in ({'min':3}, {'required':True,'max':0}):
            self.assertTrue(form.validate_question({**QUESTIONS[1],**changes}))
        q=copy.deepcopy(QUESTIONS[0]);q['options'][1]['recommended']=True
        self.assertTrue(form.validate_question(q))
        for identifier in (' ', ' a '):
            q=copy.deepcopy(QUESTIONS[0]);q['options'][0]['value']=identifier
            self.assertTrue(form.validate_question(q))
            self.assertTrue(form.validate_question({**QUESTIONS[8],'decisions':[identifier]}))

    def test_optional_fields_and_other_contract(self):
        qs=[{**QUESTIONS[0],'required':False},QUESTIONS[2]]
        errors,result=form.validate_answers({'answers':{}},qs)
        self.assertFalse(errors);self.assertEqual(result['meta']['skipped'],['choice','scale'])
        self.assertTrue(form.validate_answers({'answers':{},'other':['choice']},qs)[0])

    def test_source_profile_and_yaml_are_closed(self):
        for text in ('---\ntitle: A\nfilters: [x]\n---\nBody','---\ntitle: A\ntitle: B\n---\nBody','---\ntitle: &a A\nsubtitle: *a\n---\nBody'):
            with self.assertRaises(doc.Failure):doc.metadata(text)
        with self.assertRaises(doc.Failure):doc.normalize_fences('```{python}\nprint(1)\n```',0)
        self.assertIn('{.aq-question}',doc.normalize_fences('```{ask}\nid: a\n```',0))
        literal='````markdown\n```{ask}\nid: a\n```\n````'
        self.assertEqual(doc.normalize_fences(literal,0),literal)
        tree={'blocks':[{'t':'BlockQuote','c':[{'t':'CodeBlock','c':[['',['aq-question'],[]],'id: a']}]}]}
        with self.assertRaises(doc.Failure):doc.validate_tree(tree,{})

    def test_controls_escape_active_content(self):
        from aq_controls import control
        q={**QUESTIONS[0],'label':'<script>alert(1)</script>','recommendation':'{{< include secret >}}'}
        html=control(q)
        self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html)
        self.assertIn('form="aq-form"',html)

    def test_control_names_do_not_collide_with_user_identifiers(self):
        from aq_controls import control, FOOTER
        from html.parser import HTMLParser
        class Names(HTMLParser):
            def __init__(self):super().__init__();self.names=[]
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if 'name' in attrs:self.names.append(attrs['name'])
        parser=Names()
        parser.feed(FOOTER+control({**QUESTIONS[5],'id':'comments'})+control({**QUESTIONS[8],'items':[{'id':'note','label':'Note'},{'id':'note.comment','label':'Comment'}]}))
        self.assertEqual(len(parser.names),len(set(parser.names)))


class ArchiveTests(unittest.TestCase):
    def test_snapshot_portability_and_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);bundle,manifest,result=fixture(directory)
            root=directory/'asks';store.save(bundle,result,manifest,root=root)
            ask_id=result['meta']['ask_id'];saved=store.read_bundle(ask_id,root)
            html=(saved/'rendered/index.html').read_text()
            self.assertIn('"mode": "review"',html)
            self.assertNotIn('127.0.0.1',html)
            record=(root/(ask_id+'.md')).read_text()
            self.assertIn('producer: ask-form-qmd',record);self.assertNotIn('AQANSWER_',record.split('## Raw')[0])
            moved=directory/'moved';root.rename(moved)
            saved=store.read_bundle(ask_id,moved)
            (saved/'result.json').write_text('{}')
            with self.assertRaises(doc.Failure):store.read_bundle(ask_id,moved)

    def test_cancel_does_not_write_and_save_failure_retains_answers(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle,manifest,_=fixture(Path(temp));run=session.Collection(bundle,manifest,root=Path(temp)/'asks')
            self.assertEqual(run.finish('cancelled')[0],200)
            self.assertFalse((Path(temp)/'asks').exists())
            self.assertEqual(run.finish('submitted',BODY)[0],409)
            run=session.Collection(bundle,manifest)
            with patch.object(session,'save',side_effect=OSError('unwritable')):
                code,result=run.finish('submitted',BODY)
            self.assertEqual(code,200);self.assertEqual(result['answers'],BODY['answers'])
            self.assertIn('save_error',result['meta']);self.assertNotIn('saved',result['meta'])

    def test_stage_save_copies_verified_package(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);bundle,manifest,result=fixture(directory);root=directory/'asks'
            def stage_copy(line, **_):
                if not str(line).startswith('ASK_QMD_SAVE_REQUEST '):return
                request=json.loads(line.split(' ',1)[1])
                shutil.copytree(request['source_bundle'],request['destination_bundle'])
                shutil.copyfile(request['source_record'],request['destination_record'])
            with patch('builtins.print',side_effect=stage_copy):
                store.save(bundle,result,manifest,root=root,staged=True,stage_timeout=.5)
            self.assertTrue(Path(result['meta']['saved']).is_file())
            store.read_bundle(result['meta']['ask_id'],root)

    def test_incomplete_bundle_has_no_completed_record(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);bundle,manifest,result=fixture(directory);root=directory/'asks'
            with patch.object(store.os,'link',side_effect=OSError('publication failed')):
                with self.assertRaises(OSError):store.save(bundle,result,manifest,root=root)
            self.assertFalse(list(root.glob('*.md')))
            self.assertNotIn('saved',result['meta'])


class TransportTests(unittest.TestCase):
    def test_auth_validation_one_finish_and_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle,manifest,_=fixture(Path(temp));run=session.Collection(bundle,manifest,saving=False)
            server=session.server_for(run);thread=threading.Thread(target=server.serve_forever);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            def request(path,body=None,**headers):
                req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**headers})
                try:
                    with urlopen(req,timeout=3) as response:return response.status,response.read()
                except HTTPError as error:return error.code,error.read()
            suffix='?t='+run.token
            try:
                self.assertEqual(request('/')[0],403)
                self.assertEqual(request('/'+suffix,Origin='https://example.com')[0],403)
                self.assertEqual(request('/submit'+suffix,{'answers':{}})[0],400)
                with ThreadPoolExecutor(2) as pool:
                    results=list(pool.map(lambda _:request('/submit'+suffix,BODY)[0],range(2)))
                self.assertEqual(sorted(results),[200,409])
                code,data=request('/state'+suffix)
                self.assertEqual(json.loads(data)['answers'],BODY['answers'])
                self.assertEqual(request('/ack'+suffix,{})[0],200)
                self.assertTrue(run.ack.wait(1))
            finally:
                server.shutdown();server.server_close();thread.join()


@unittest.skipUnless(os.environ.get('ASK_QMD_LIVE')=='1','real Quarto opt-in')
class LiveTests(unittest.TestCase):
    def test_compiler_independent_copy_and_no_project_inheritance(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);copied=directory/'skill';shutil.copytree(SKILL,copied)
            source=directory/'example.qmd';shutil.copyfile(copied/'assets/example.qmd',source)
            (directory/'_quarto.yml').write_text('project:\n  pre-render: definitely-not-a-real-command\n')
            import subprocess
            result=subprocess.run(['uv','run',str(copied/'scripts/ask_form_qmd.py'),'validate',str(source),'--json'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            manifest=doc.compile_form(source,directory/'bundle')
            html=(directory/'bundle/rendered/index.html').read_text()
            self.assertIn('aq-question-direction',html);self.assertIn('rd-diagram',html)
            self.assertIn(doc.SNAPSHOT,html)
            self.assertNotRegex(html,r'AQHTML[a-f0-9]{32}')
            self.assertEqual(html.count('<fieldset class="aq-controls">'),9)
            self.assertEqual(manifest['renderer'],'quarto 1.9.38')
            compiled=json.loads((directory/'bundle/form.json').read_text())
            self.assertIn('structured answers',compiled['question_context']['direction'][0]['markdown'])
            errors,result=form.validate_answers({'answers':{'direction':'native','reasoning':'Archive survives moves'}},compiled['questions'])
            self.assertFalse(errors)
            result.update(status='submitted');result['meta'].update(ask_id=store.new_id('Portable'),duration_s=1)
            store.save(directory/'bundle',result,manifest,root=directory/'asks')
            source.unlink();shutil.rmtree(copied);(directory/'asks').rename(directory/'moved')
            saved=store.read_bundle(result['meta']['ask_id'],directory/'moved')
            self.assertIn('Archive survives moves',(saved/'rendered/index.html').read_text())

    def test_duplicate_keys_nested_questions_and_raw_html_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);quarto=doc.engine(directory)
            q='```{ask}\nid: a\ntype: short_text\nlabel: A\n```\n'
            for body in ('::: {.callout-note}\n'+q+':::\n',q+'\n<script>alert(1)</script>',q.replace('label: A','label: A\nlabel: B')):
                source=directory/'source.qmd';source.write_text('---\ntitle: Bad\n---\n'+body)
                with self.assertRaises(doc.Failure):doc.parse_source(source,directory,quarto)

    def test_source_locations_and_reserved_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);quarto=doc.engine(directory);source=directory/'source.qmd'
            q='```{ask}\nid: form\ntype: short_text\nlabel: A\n```\n'
            for second in (q,q.replace('type: short_text','type: unknown')):
                source.write_text('---\ntitle: Bad\n---\n'+q+'\n'+second)
                with self.assertRaises(doc.Failure) as caught:doc.parse_source(source,directory,quarto)
                self.assertEqual(caught.exception.result['location'],'line 10')
            for ident in ('aq-form','rd-mermaid-theme'):
                source.write_text('---\ntitle: Bad\n---\n'+q+'\n# Reserved {#'+ident+'}\n')
                with self.assertRaises(doc.Failure):doc.parse_source(source,directory,quarto)

    def test_question_images_have_portable_transcript_links(self):
        import base64
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);quarto=doc.engine(directory)
            (directory/'pixel.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='))
            source=directory/'source.qmd'
            source.write_text('---\ntitle: Image\nassets:\n  pixel: pixel.png\n---\n```{ask}\nid: a\ntype: short_text\nlabel: A\nhelp: "![Pixel](asset:pixel)"\n```\n')
            parsed=doc.parse_source(source,directory,quarto)
            self.assertIn('](assets/pixel.png)',parsed['question_context']['a'][0]['markdown'])
            compiled={'title':'Image','questions':parsed['questions'],'context':parsed['context'],'slots':parsed['slots'],'question_context':parsed['question_context']}
            record=store.transcript(compiled,{'answers':{},'meta':{'duration_s':1}},{'id':'fixture','created':'now','submitted':'now'})
            self.assertIn('](_bundles/fixture/assets/pixel.png)',record.split('## Raw')[0])


if __name__=='__main__':
    unittest.main()
