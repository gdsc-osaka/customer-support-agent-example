IMAGE_PROMPT_FORMAT = """
{
  "task": "generate_image",
  "image_type": "travel_itinerary_cover",
  "canvas": {
    "aspect_ratio": "3:4",
  },
  "text_elements": [
    {
      "id": "main_title",
      "text": "AI時代の仕事術",
      "language": "ja",
      "priority": 1,
      "placement": "center-left",
      "font_style": <the_most_appropriate_font_for_each_test_element>,
      "size": "very large",
      "color": "white",
      "stroke": "thick black outline",
      "line_breaks": ["AI時代の", "仕事術"]
    }
  ],
  "visual_elements": [
    {
      "subject": "a focused Japanese office worker using a laptop",
      "placement": "right side",
      "style": "clean commercial illustration"
    }
  ],
  "composition": {
    "hierarchy": "main_title must be the largest and most readable element",
    "safe_area": "keep all text away from edges by 8%",
    "background": "dark blue gradient with subtle tech patterns"
  },
  "constraints": {
    "must_include_exact_text": ["AI時代の仕事術"],
    "no_extra_text": true,
    "avoid": [
      "misspelled Japanese",
      "tiny unreadable text",
      "random letters",
      "watermarks",
      "logos"
    ]
  }
}
"""