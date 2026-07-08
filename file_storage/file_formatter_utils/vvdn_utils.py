import fitz

def vvdn_pdf(input_path, output_path):
    doc = fitz.open(input_path)

    for page in doc:
        logo_rect = fitz.Rect(968, 784.5, 1130, 813.5)
        page.add_redact_annot(logo_rect, fill=(1, 1, 1))

        description_rect = fitz.Rect(1, 300, 35, 960)
        page.add_redact_annot(description_rect, fill=(1, 1, 1))

        if page.search_for("PROJECT ID"):
            project_id_rect = fitz.Rect(970, 720, 1155, 738)
            page.add_redact_annot(project_id_rect, fill=(1, 1, 1))

        page.apply_redactions()

    doc.save(output_path, garbage=4, clean=True)
    doc.close()

# import fitz

# WORDS_TO_REDACT = [
#     "vvdn",
#     "vvdn_pts",
#     "VVDN Technologies",
#     "THIS INFORMATION IS CONFIDENTIAL AND PROPRIETARY TO",
# "VVDN TECHNOLOGIES AND ITS WORLDWIDE SUBSIDIARIES &",
# "AFFILIATES. IT MAY NOT BE DISCLOSED TO ANYONE, OTHER,"
# "THAN VVDN PERSONNEL, WITHOUT WRITTEN AUTHORIZATION",
# "FROM AN AUTHORIZED REPRESENTATIVE OF VVDN TECHNOLOGIES" 
# ]

# def vvdn_pdf(input_path, output_path):
#     doc = fitz.open(input_path)

#     for page in doc:
#         for word in WORDS_TO_REDACT:
#             matches = page.search_for(word)

#             for rect in matches:
#                 # Slightly expand the area so the whole text is covered
#                 expanded_rect = fitz.Rect(
#                     rect.x0 - 2,
#                     rect.y0 - 2,
#                     rect.x1 + 2,
#                     rect.y1 + 2
#                 )

#                 page.add_redact_annot(expanded_rect, fill=(1, 1, 1))

#         page.apply_redactions()

#     doc.save(output_path, garbage=4, clean=True)
#     doc.close()