const { onRequest } = require("firebase-functions/v2/https");
const logger = require("firebase-functions/logger");

exports.generateMCQs = onRequest(
  {
    cors: true,
    timeoutSeconds: 300,
    memory: "1GiB"
  },
  async (req, res) => {
    try {
      if (req.method !== "POST") {
        return res.status(405).json({
          error: "POST required"
        });
      }

      const { text } = req.body || {};

      if (!text || text.trim().length < 100) {
        return res.status(400).json({
          error: "Not enough PDF text"
        });
      }

      const apiKey = process.env.GEMINI_API_KEY;

      if (!apiKey) {
        return res.status(500).json({
          error: "Gemini API key is not configured"
        });
      }

      const prompt = `
You are an expert Indian current-affairs exam question generator.

Convert the following current-affairs/news text into high-quality MCQs.

Rules:
- Generate as many useful MCQs as possible, maximum 50.
- Every MCQ must have EXACTLY 5 options.
- Options must be A, B, C, D and E.
- Only ONE option must be correct.
- Questions must be based ONLY on the supplied text.
- Do not invent facts.
- Avoid duplicate questions.
- Include important facts, dates, people, places, organisations, schemes, reports, awards, defence, science, sports, economy and international affairs when present.
- Return ONLY valid JSON.

JSON format:
{
  "questions": [
    {
      "q": "Question text",
      "o": ["Option A", "Option B", "Option C", "Option D", "Option E"],
      "a": 0,
      "explanation": "Short explanation"
    }
  ]
}

The "a" value must be:
0 for A
1 for B
2 for C
3 for D
4 for E

CURRENT-AFFAIRS TEXT:
${text.slice(0, 120000)}
`;

      const response = await fetch(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" +
          encodeURIComponent(apiKey),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            contents: [
              {
                parts: [
                  {
                    text: prompt
                  }
                ]
              }
            ],
            generationConfig: {
              temperature: 0.2,
              responseMimeType: "application/json"
            }
          })
        }
      );

      const data = await response.json();

      if (!response.ok) {
        logger.error("Gemini error", data);
        return res.status(500).json({
          error: "AI generation failed"
        });
      }

      const output =
        data?.candidates?.[0]?.content?.parts?.[0]?.text;

      if (!output) {
        return res.status(500).json({
          error: "AI returned no questions"
        });
      }

      let result;

      try {
        result = JSON.parse(output);
      } catch (e) {
        const cleaned = output
          .replace(/^```json\s*/i, "")
          .replace(/\s*```$/i, "")
          .trim();

        result = JSON.parse(cleaned);
      }

      const questions = Array.isArray(result.questions)
        ? result.questions
            .filter(q =>
              q &&
              typeof q.q === "string" &&
              Array.isArray(q.o) &&
              q.o.length === 5 &&
              Number.isInteger(q.a) &&
              q.a >= 0 &&
              q.a <= 4
            )
            .map(q => ({
              q: q.q.trim(),
              o: q.o.map(String),
              a: q.a,
              explanation: String(q.explanation || "")
            }))
        : [];

      if (!questions.length) {
        return res.status(500).json({
          error: "AI did not produce valid 5-option MCQs"
        });
      }

      return res.json({
        questions
      });

    } catch (error) {
      logger.error(error);

      return res.status(500).json({
       
