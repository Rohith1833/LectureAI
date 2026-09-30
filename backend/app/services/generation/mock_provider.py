import json
import re
from typing import Optional, Dict, Any, List
from app.services.generation.base import LLMGenerationRequest, LLMGenerationResponse
from app.services.generation.errors import LLMProviderError


class MockLLMProvider:
  """Deterministic mock provider simulating vendor API behaviors in unit and integration tests."""

  def __init__(
      self,
      scenario: str = "success",
      error_message: str = "Simulated API failure",
      custom_response: Optional[str] = None
  ):
    self.scenario = scenario.lower()
    self.error_message = error_message
    self.custom_response = custom_response
    self.calls: List[LLMGenerationRequest] = []

  async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
    """Simulates asynchronous structured text generation based on the configured scenario."""
    self.calls.append(request)

    if self.scenario == "provider_failure":
      raise LLMProviderError(self.error_message)

    if self.scenario == "rate_limit":
      raise LLMProviderError("Rate limit exceeded: 429 Too Many Requests (Retry-After: 30)")

    if self.scenario == "timeout":
      raise LLMProviderError("Request timed out after 30.0s")

    if self.scenario == "malformed_output":
      return LLMGenerationResponse(
          raw_response=self.custom_response or "invalid-raw-text-{malformed-json",
          structured_output=None,
          token_usage={"prompt_tokens": 15, "completion_tokens": 5},
          model_name="mock-malformed-model"
      )

    if self.scenario == "malformed_slides_schema":
      return LLMGenerationResponse(
          raw_response='{"status": "ok", "unexpected_payload": []}',
          structured_output={"status": "ok", "unexpected_payload": []},
          token_usage={"prompt_tokens": 15, "completion_tokens": 5},
          model_name="mock-malformed-schema-model"
      )

    is_slide_schema = False
    if request.json_schema and isinstance(request.json_schema, dict):
      props = request.json_schema.get("properties", {})
      if "slides" in props:
        is_slide_schema = True

    if is_slide_schema:
      if self.scenario == "invalid_citation":
        structured_data = {
            "slides": [
                {
                    "slide_type": "CONTENT",
                    "title": "Fabricated Reference Slide",
                    "content": ["This slide cites fabricated IDs."],
                    "speaker_notes": "Invalid citation notes.",
                    "source_node_ids": ["fabricated_source_node_999"],
                    "evidence_ids": ["fabricated_evidence_999"]
                }
            ]
        }
        return LLMGenerationResponse(
            raw_response=json.dumps(structured_data),
            structured_output=structured_data,
            token_usage={"prompt_tokens": 50, "completion_tokens": 25},
            model_name="mock-invalid-citation-model"
        )

      # Success slide scenario
      if self.custom_response:
        try:
          structured_data = json.loads(self.custom_response)
        except Exception:
          structured_data = {"slides": []}
      else:
        # Extract supplied IDs, titles, and content excerpts from prompt
        # Context entities are formatted as: "- [CATEGORY] (node_id) Title: content"
        source_node_ids = []
        titles = []
        contents = []
        for line in request.prompt.split("\n"):
          line = line.strip()
          if line.startswith("- [") and " (" in line and ") " in line:
            id_start = line.index("(") + 1
            id_end = line.index(")", id_start)
            nid = line[id_start:id_end]
            rest = line[id_end + 1:].strip()
            if ":" in rest:
              # Take everything up to the first colon after title as title, remainder as content
              # E.g. "Topic 2.1: Cellular Respiration Overview: Cellular respiration transforms..."
              # If there are multiple colons, match the one that precedes content
              colons = [i for i, ch in enumerate(rest) if ch == ":"]
              if len(colons) > 1:
                # The last colon separates title from content
                t = rest[:colons[-1]].strip()
                c = rest[colons[-1] + 1:].strip()
              else:
                parts = rest.split(":", 1)
                t = parts[0].strip()
                c = parts[1].strip()
            else:
              t = rest
              c = rest
            source_node_ids.append(nid)
            titles.append(t)
            contents.append(c)

        evidence_ids = re.findall(r"\[Evidence ID:\s*([a-zA-Z0-9_-]+)\]", request.prompt)

        slides = []
        unit_title = titles[0] if titles else "Curriculum Overview"
        unit_sid = [source_node_ids[0]] if source_node_ids else []
        unit_content_snippet = (
            contents[0][:200].strip() if contents and contents[0]
            else f"Introductory syllabus and objectives for {unit_title}"
        )

        # Title slide
        slides.append({
            "slide_type": "TITLE",
            "title": unit_title,
            "content": [unit_content_snippet],
            "speaker_notes": f"Welcome to {unit_title}. This unit establishes core theoretical concepts.",
            "source_node_ids": unit_sid,
            "evidence_ids": [evidence_ids[0]] if evidence_ids else []
        })

        # Content slides for each entity
        if len(source_node_ids) > 1:
          for idx, sid in enumerate(source_node_ids[1:], start=1):
            t_name = titles[idx].strip() if idx < len(titles) else f"Academic Topic {idx}"
            ev_list = [evidence_ids[idx % len(evidence_ids)]] if evidence_ids else []
            body_snippet = (
                contents[idx][:200].strip() if idx < len(contents) and contents[idx]
                else f"Foundational concepts and principles of {t_name}."
            )
            slides.append({
                "slide_type": "CONTENT",
                "title": t_name,
                "content": [
                    body_snippet,
                    f"Theoretical formulation and mathematical derivations of {t_name}.",
                    f"Practical applications and case study analysis."
                ],
                "speaker_notes": f"Detailed educational exposition for {t_name}.",
                "source_node_ids": [sid],
                "evidence_ids": ev_list
            })
        else:
          slides.append({
              "slide_type": "CONTENT",
              "title": f"{unit_title}: Key Concepts",
              "content": [
                  unit_content_snippet,
                  "Systematic structural properties and formal definitions.",
                  "Methodological analysis and applied examples."
              ],
              "speaker_notes": "Exposition of core unit themes.",
              "source_node_ids": unit_sid,
              "evidence_ids": [evidence_ids[0]] if evidence_ids else []
          })

        structured_data = {"slides": slides}

      return LLMGenerationResponse(
          raw_response=json.dumps(structured_data),
          structured_output=structured_data,
          token_usage={"prompt_tokens": 100, "completion_tokens": 50},
          model_name="mock-slides-model"
      )

    # Default Q&A behavior for backwards compatibility
    if self.scenario == "invalid_citation":
      structured_data = {
          "answer": "This is an answer referencing an invalid citation ID.",
          "claims": [
              {
                  "claim_id": "c_mock_1",
                  "text": "This assertion is backed by an unknown citation.",
                  "citation_ids": ["S99"],
                  "grounding_status": "UNSUPPORTED"
              }
          ]
      }
      return LLMGenerationResponse(
          raw_response="Answer text referencing invalid citation [S99].",
          structured_output=structured_data,
          token_usage={"prompt_tokens": 20, "completion_tokens": 10},
          model_name="mock-invalid-citation-model"
      )

    # Default 'success' Q&A scenario
    structured_data = {
        "answer": self.custom_response or "This is a deterministic correct grounded answer.",
        "claims": [
            {
                "claim_id": "c_mock_1",
                "text": "This is a statement.",
                "citation_ids": ["S1"],
                "grounding_status": "SUPPORTED"
            }
        ]
    }
    return LLMGenerationResponse(
        raw_response=self.custom_response or "This is a deterministic correct grounded answer [S1].",
        structured_output=structured_data,
        token_usage={"prompt_tokens": 30, "completion_tokens": 15},
        model_name="mock-success-model"
    )
