import opennyai.ner as InLegalNER
from opennyai import RhetoricalRolePredictor
from opennyai import ExtractiveSummarizer
from wasabi import msg
import copy


class Pipeline:
    def __init__(self, components=None, use_gpu=True, verbose=False):
        if components is None:
            components = ['NER', 'Rhetorical_Role', 'Summarizer']
        self.components = components
        self.__verbose__ = verbose
        if 'NER' in components:
            if self.__verbose__:
                msg.info('Loading NER...')
            self.__ner_extractor__ = InLegalNER.load(use_gpu=use_gpu)

        if 'Rhetorical_Role' in components or 'Summarizer' in components:
            if self.__verbose__:
                msg.info('Loading Rhetorical Role...')
            self.__rr_model__ = RhetoricalRolePredictor(use_gpu=use_gpu, verbose=verbose)

        if 'Summarizer' in components:
            if self.__verbose__:
                msg.info('Loading Extractive summarizer...')
            self.__summarizer__ = ExtractiveSummarizer(use_gpu=use_gpu, verbose=verbose)

    @staticmethod
    def __combine_model_outputs__(ner_json_results=None, rr_output=None, summary_output=None):
        '''combines the outputs of 3 models into single list'''
        combined_results = {}
        ####### Add NER results
        if ner_json_results:
            for doc_ner in ner_json_results:
                doc_id = doc_ner['id'].split('_')[1]
                if combined_results.get(doc_id) is None:
                    combined_results[doc_id] = {'id': doc_id, 'data': {'text': doc_ner['data']['text']}}

                combined_results[doc_id]['ner_annotations'] = doc_ner['annotations']

        ####### Add RR results
        if rr_output:
            for doc_rr in rr_output:
                doc_id = doc_rr['id'].split('_')[1]
                if combined_results.get(doc_id) is None:
                    combined_results[doc_id] = {'id': doc_id, 'data': {'text': doc_rr['data']['text']}}

                combined_results[doc_id]['rr_annotations'] = doc_rr['annotations']

        ####### Add summary results
        if summary_output:
            for doc_summary in summary_output:
                doc_id = doc_summary['id'].split('_')[1]
                combined_results[doc_id]['summary'] = doc_summary['summaries']

        return [result for doc_id, result in combined_results.items()]

    @staticmethod
    def __postprocess_ner_to_sentence_level__(doc):
        id = "LegalNER_" + doc.user_data['doc_id']
        final_output = InLegalNER.get_json_from_spacy_doc(doc)
        output = {'id': id, 'annotations': [{'result': []}],
                  'data': {'text': doc.text, 'original_text': doc.user_data['original_text']}}
        for sent in doc.sents:
            import uuid
            uid = uuid.uuid4()
            id = uid.hex
            temp = copy.deepcopy({"id": id,
                                  "type": "labels",
                                  "value": {
                                      "start": sent.start_char,
                                      "end": sent.end_char,
                                      "text": sent.text,
                                      "entities": [],
                                  }, "to_name": "text",
                                  "from_name": "label"
                                  })
            for entity in final_output['annotations'][0]['result']:
                if entity['value']['start'] >= temp['value']['start'] and entity['value']['end'] <= temp['value'][
                    'end']:
                    temp['value']['entities'].append(entity)
            output['annotations'][0]['result'].append(temp)
        return output

    def __call__(self, data):
        ner_json_results, self._ner_model_output, self._rr_model_output, self._summarizer_model_output = None, None, None, None
        if 'NER' in self.components:
            self._ner_model_output = self.__ner_extractor__(data, verbose=self.__verbose__)
            if not isinstance(self._ner_model_output, list):
                self._ner_model_output = [self._ner_model_output]
            ner_json_results = [self.__postprocess_ner_to_sentence_level__(doc) for doc in self._ner_model_output]

        if 'Rhetorical_Role' in self.components or 'Summarizer' in self.components:
            self._rr_model_output = self.__rr_model__(data)

        if 'Summarizer' in self.components:
            self._summarizer_model_output = self.__summarizer__(self._rr_model_output)

        return self.__combine_model_outputs__(ner_json_results, self._rr_model_output, self._summarizer_model_output)
