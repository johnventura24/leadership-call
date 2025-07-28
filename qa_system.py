import logging
from typing import Dict, Any, List, Optional
from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.schema import HumanMessage, AIMessage
from datetime import datetime
import json

from config import config
from knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)

class QASystem:
    """Question-answering system using the knowledge base"""
    
    def __init__(self, knowledge_base: KnowledgeBase):
        self.knowledge_base = knowledge_base
        self.llm = ChatOpenAI(
            openai_api_key=config.openai_api_key,
            model_name=config.qa_model,
            temperature=config.temperature,
            max_tokens=config.max_tokens
        )
        
        # System prompt for the QA system
        self.system_prompt = """You are a knowledgeable assistant that answers questions based on leadership meeting notes and FAQs.

**Instructions:**
1. Use ONLY the provided context to answer questions
2. If the context doesn't contain enough information to answer fully, say so clearly
3. When citing information, reference the document type (FAQ or meeting notes) and document title
4. For FAQ questions, provide the exact question-answer pairs when relevant
5. For meeting notes, reference the specific meeting or topic
6. Be concise but comprehensive
7. If multiple sources support the answer, mention all relevant sources
8. If the question is about recent decisions or actions, prioritize meeting notes
9. If the question is about policies or procedures, prioritize FAQs

**Context Types:**
- FAQ: Frequently asked questions and their answers
- Meeting Notes: Leadership meeting discussions, decisions, and action items

**Response Format:**
- Start with a direct answer
- Provide supporting details from the context
- End with source references in format: [Source: Document Type - Document Title]
"""
        
        # Create the prompt template
        self.prompt_template = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(self.system_prompt),
            HumanMessagePromptTemplate.from_template("""
Context Information:
{context}

Question: {question}

Please provide a comprehensive answer based on the context provided above.
""")
        ])
    
    def _format_context(self, context_items: List[Dict[str, Any]]) -> str:
        """Format context items for the prompt"""
        formatted_context = []
        
        for i, item in enumerate(context_items, 1):
            content = item['content']
            metadata = item['metadata']
            document_type = item['document_type']
            document_title = item['document_title']
            section_type = item['section_type']
            relevance_score = item['relevance_score']
            
            # Format based on document type
            if section_type == 'faq' and 'question' in item:
                formatted_item = f"""
Source {i}: FAQ - {document_title}
Question: {item['question']}
Answer: {item['answer']}
(Relevance: {relevance_score:.3f})
"""
            else:
                formatted_item = f"""
Source {i}: {document_type.upper()} - {document_title}
Section: {section_type.replace('_', ' ').title()}
Content: {content}
(Relevance: {relevance_score:.3f})
"""
            
            formatted_context.append(formatted_item)
        
        return "\n" + "="*50 + "\n".join(formatted_context)
    
    def answer_question(self, question: str, max_context_items: int = 5) -> Dict[str, Any]:
        """Answer a question using the knowledge base"""
        try:
            # Get relevant context from knowledge base
            context_items = self.knowledge_base.get_relevant_context(
                question, 
                max_chunks=max_context_items
            )
            
            if not context_items:
                return {
                    'answer': "I don't have enough information in my knowledge base to answer this question. Please check if the relevant documents have been added to the system.",
                    'sources': [],
                    'context_used': [],
                    'confidence': 0.0,
                    'question': question,
                    'timestamp': datetime.now().isoformat()
                }
            
            # Format context for the prompt
            formatted_context = self._format_context(context_items)
            
            # Generate the prompt
            prompt = self.prompt_template.format_messages(
                context=formatted_context,
                question=question
            )
            
            # Get response from the LLM
            response = self.llm(prompt)
            answer = response.content
            
            # Extract source information
            sources = []
            for item in context_items:
                source_info = {
                    'document_type': item['document_type'],
                    'document_title': item['document_title'],
                    'section_type': item['section_type'],
                    'relevance_score': item['relevance_score']
                }
                
                if item['section_type'] == 'faq' and 'question' in item:
                    source_info['faq_question'] = item['question']
                
                sources.append(source_info)
            
            # Calculate confidence based on relevance scores
            avg_relevance = sum(item['relevance_score'] for item in context_items) / len(context_items)
            confidence = max(0.0, 1.0 - avg_relevance)  # Convert distance to confidence
            
            return {
                'answer': answer,
                'sources': sources,
                'context_used': context_items,
                'confidence': confidence,
                'question': question,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error answering question: {e}")
            return {
                'answer': f"I encountered an error while processing your question: {str(e)}",
                'sources': [],
                'context_used': [],
                'confidence': 0.0,
                'question': question,
                'timestamp': datetime.now().isoformat()
            }
    
    def batch_answer_questions(self, questions: List[str]) -> List[Dict[str, Any]]:
        """Answer multiple questions in batch"""
        results = []
        
        for question in questions:
            result = self.answer_question(question)
            results.append(result)
        
        return results
    
    def get_faq_suggestions(self, query: str, max_suggestions: int = 3) -> List[Dict[str, Any]]:
        """Get FAQ suggestions based on a query"""
        try:
            # Search specifically in FAQs
            faq_results = self.knowledge_base.search_faqs(query, max_suggestions)
            
            suggestions = []
            for doc, score in faq_results:
                if doc.metadata.get('section_type') == 'faq':
                    question = doc.metadata.get('question', '')
                    answer = doc.metadata.get('answer', '')
                    
                    if question and answer:
                        suggestions.append({
                            'question': question,
                            'answer': answer,
                            'relevance_score': score,
                            'document_title': doc.metadata.get('document_title')
                        })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting FAQ suggestions: {e}")
            return []
    
    def search_meeting_topics(self, topic: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search for specific topics in meeting notes"""
        try:
            # Search in meeting notes
            meeting_results = self.knowledge_base.search_meeting_notes(topic, max_results)
            
            topics = []
            for doc, score in meeting_results:
                topics.append({
                    'content': doc.page_content,
                    'document_title': doc.metadata.get('document_title'),
                    'section_title': doc.metadata.get('section_title'),
                    'relevance_score': score,
                    'document_id': doc.metadata.get('document_id')
                })
            
            return topics
            
        except Exception as e:
            logger.error(f"Error searching meeting topics: {e}")
            return []
    
    def get_conversation_context(self, question: str, conversation_history: List[Dict[str, str]]) -> Dict[str, Any]:
        """Get context for a question considering conversation history"""
        # Extract previous questions and answers for context
        recent_context = []
        for item in conversation_history[-3:]:  # Use last 3 exchanges
            if item.get('question') and item.get('answer'):
                recent_context.append(f"Q: {item['question']}\nA: {item['answer']}")
        
        # Modify the question to include conversational context
        if recent_context:
            contextual_question = f"""
Previous conversation:
{chr(10).join(recent_context)}

Current question: {question}
"""
        else:
            contextual_question = question
        
        return self.answer_question(contextual_question)
    
    def explain_answer(self, question: str, answer_result: Dict[str, Any]) -> str:
        """Provide an explanation of how the answer was generated"""
        sources = answer_result.get('sources', [])
        confidence = answer_result.get('confidence', 0.0)
        
        explanation = f"""
**Answer Generation Explanation:**

**Question:** {question}

**Confidence Level:** {confidence:.2f} (0.0 = low, 1.0 = high)

**Sources Used:**
"""
        
        for i, source in enumerate(sources, 1):
            doc_type = source['document_type']
            doc_title = source['document_title']
            relevance = source['relevance_score']
            
            explanation += f"""
{i}. {doc_type.upper()}: {doc_title}
   - Relevance Score: {relevance:.3f}
   - Section: {source['section_type'].replace('_', ' ').title()}
"""
            
            if source.get('faq_question'):
                explanation += f"   - FAQ Question: {source['faq_question']}\n"
        
        if not sources:
            explanation += "No relevant sources found in the knowledge base."
        
        return explanation
    
    def validate_answer_quality(self, answer_result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the quality of an answer"""
        confidence = answer_result.get('confidence', 0.0)
        sources = answer_result.get('sources', [])
        answer = answer_result.get('answer', '')
        
        quality_metrics = {
            'has_sources': len(sources) > 0,
            'confidence_score': confidence,
            'answer_length': len(answer),
            'source_diversity': len(set(source['document_type'] for source in sources)),
            'high_confidence': confidence > 0.7,
            'sufficient_context': len(sources) >= 2
        }
        
        # Overall quality score
        quality_score = (
            0.3 * quality_metrics['has_sources'] +
            0.3 * quality_metrics['confidence_score'] +
            0.2 * min(1.0, quality_metrics['answer_length'] / 100) +
            0.2 * min(1.0, quality_metrics['source_diversity'] / 2)
        )
        
        quality_metrics['overall_quality'] = quality_score
        quality_metrics['quality_level'] = (
            'High' if quality_score > 0.7 else
            'Medium' if quality_score > 0.4 else
            'Low'
        )
        
        return quality_metrics 