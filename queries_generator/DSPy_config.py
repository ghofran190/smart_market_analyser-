
import json
from queries_generator.models import AnalysisOutput, QuestionQueries, SearchQuery
from queries_generator.utils import parse_search_queries
import dspy
from utils.logger import get_logger
logger =get_logger(__name__)

# ============================================================================
# DSPy Signatures
# ============================================================================

class QueryGenerationSignature(dspy.Signature):
    """
    You are a market research expert. Given a market analysis section, a major question,
    and project context, generate 3-4 highly targeted search engine queries.

    Rules:
    - Each query must cover a DIFFERENT angle (e.g., market size, trends, competitors, regulations, user pain points)
    - Queries must NOT be redundant or semantically similar
    - Queries must be directly aligned with the question
    - Mix languages/perspectives to maximise URL diversity (e.g., industry reports, news, academic, local market)
    - Each query should mention the target market (SaaS for customer industry)
    - Example of correct escaping: "query": "This is a \"quoted\" term"
    - Return ONLY valid JSON — no markdown, no extra text
    """

    project_info: str = dspy.InputField(desc="JSON string with project context")
    section: str = dspy.InputField(desc="The market analysis section being addressed")
    question: str = dspy.InputField(desc="The major question to answer")
    num_queries: int = dspy.InputField(desc="Number of queries to generate (3 or 4)")

    queries_json: str = dspy.OutputField(
        desc="""JSON array of objects with keys: "query" (string), "angle" (string), "relevance_score" (float 0-1).
Example:
[
  {"query": "taille de marché de logiciel SaaS hôtellerie France 2024", "angle": "global market sizing", "relevance_score": 0.95},
  {"query": "tendances logiciels hôtellerie indépendante Europe 2024", "angle": "regional trends francophone", "relevance_score": 0.92}
]"""
    )


class DeduplicationSignature(dspy.Signature):
    """
    You are a search query quality auditor.
    Review a list of search queries and remove or rewrite any that are:
    - Semantically redundant (would return same URLs)
    - Not directly relevant to the question
    - Too generic or vague
    Return queries in the same format as input: numbered lines with pipe separators.
    Return ONLY valid JSON — no markdown, no extra text.
    """

    question: str = dspy.InputField(desc="The major question these queries address")
    queries_json: str = dspy.InputField(desc="JSON array of candidate queries with angle and relevance_score")
    max_queries: int = dspy.InputField(desc="Maximum number of queries to keep")

    refined_queries_json: str = dspy.OutputField(
        desc="JSON array of deduplicated and refined queries, same structure as input,one per line"
    )


# ============================================================================
# DSPy Modules
# ============================================================================


class QueryGeneratorModule(dspy.Module):
    """Generates search queries for a single question."""

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(QueryGenerationSignature)

    def forward(
        self,
        project_info: dict,
        section: str,
        question: str,
        num_queries: int = 4,
    ) -> list[SearchQuery]:
        result = self.generate(
            project_info=json.dumps(project_info, ensure_ascii=False),
            section=section,
            question=question,
            num_queries=num_queries,
        )
        return self._parse_queries(result.queries_json)

    def _parse_queries(self, raw: str) -> list[SearchQuery]:
        return parse_search_queries(raw)


class DeduplicationModule(dspy.Module):
    """Deduplicates and refines queries for a single question."""

    def __init__(self):
        super().__init__()
        self.refine = dspy.ChainOfThought(DeduplicationSignature)

    def forward(
        self,
        question: str,
        queries: list[SearchQuery],
        max_queries: int = 4,
    ) -> list[SearchQuery]:
        queries_json = json.dumps(
            [
                {"query": q.query, "angle": q.angle, "relevance_score": q.relevance_score}
                for q in queries
            ],
            ensure_ascii=False,
        )
        result = self.refine(
            question=question,
            queries_json=queries_json,
            max_queries=max_queries,
        )
        return self._parse_queries(result.refined_queries_json)

    def _parse_queries(self, raw: str) -> list[SearchQuery]:
        return parse_search_queries(raw)


class MarketAnalysisQueryPipeline(dspy.Module):
    """
    Full pipeline: for each question in a section, generate + deduplicate queries.
    """

    def __init__(self):
        super().__init__()
        self.query_generator = QueryGeneratorModule()
        self.deduplicator = DeduplicationModule()

    def forward(
        self,
        project_info: dict,
        section: str,
        questions: list[str],
        num_queries: int = 4,
    ) -> AnalysisOutput:
        output = AnalysisOutput(section=section)

        for question in questions:
            logger.info(f"  ↳ Generating queries for: {question[:60]}...")

            raw_queries = self.query_generator(
                project_info=project_info,
                section=section,
                question=question,
                num_queries=num_queries,
            )

            refined_queries = self.deduplicator(
                question=question,
                queries=raw_queries,
                max_queries=num_queries,
            )

            refined_queries.sort(key=lambda q: q.relevance_score, reverse=True)

            output.question_queries.append(
                QuestionQueries(question=question, queries=refined_queries)
            )

        return output
