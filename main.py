import re
import os
import shutil
import data
import json
from bs4 import BeautifulSoup
from bs4.element import Tag, NavigableString
import Levenshtein


STYLE_MAP_PATH = 'stylemap.txt'
OUTPUT_DIRECTORY = 'roadmap-to-html'
IMG_PATH = 'img'
RAW_INDEX_PATH = os.path.join(OUTPUT_DIRECTORY, 'raw_index.html')
NICE_INDEX_PATH = os.path.join(OUTPUT_DIRECTORY, 'nice_index.html')

TOC_CLASSES = {'toc1', 'toc2', 'toc3', 'toc4'}

TOC_CONTENT_SIGNIFIER = "_Toc"

CHAPTER_TITLES_TO_EXCLUDE = [
    'questions about the guide',
    'questions about you',
    'connecting with root & rebound',
    'any other comments/feedback',
    'follow-up survey contact information'
]


def idx_to_str(index):
    return "{num:06d}".format(num=index)


def get_soup_index(soup, element):
    indexes = []
    parent_element = element
    while not parent_element.parent == soup:
        indexes.append(
            parent_element.parent.index(
                parent_element))
        parent_element = parent_element.parent
    indexes.append(soup.index(parent_element))
    return '.'.join([idx_to_str(index) for index in reversed(indexes)])


def is_toc_content(element_id):
    if element_id:
        return TOC_CONTENT_SIGNIFIER in element_id
    else:
        return False


def is_toc_item(class_name):
    return class_name in TOC_CLASSES


def write_prettified_raw_index(soup):
    with open(NICE_INDEX_PATH, 'w') as index_file:
        index_file.write(soup.prettify())


def remove_trailing_footnote_text(string):
    return re.sub(r"\[\d+\]", '', string)


def get_toc_content_text(item, soup):
    if item.parent != soup:
        return item.parent.text
    elif item.next_sibling:
        if not item.next_sibling.text:
            if item.next_sibling.next_sibling:
                return item.next_sibling.next_sibling.text
        return item.next_sibling.text
    else:
        return item.text


def get_appendix_toc_content_text(item, soup):
    """Get the text of the next sibling

    Example HTML:
        <div class="appendix">
          Appendix E
        </div>
        <div class="appendixtitle">
          Franchise Tax Board, Identity Theft Affidavit
        </div>
    """
    return item.next_sibling.text


def is_valid_toc_content_item(prospective_item):
    """
    if this and next sibling are both toc items,
    and they both have no text content,
    then this one should be disregarded
    """
    next_sibling = prospective_item.next_sibling
    if isinstance(next_sibling, Tag):
        if is_toc_content(next_sibling.get('id')):
            if (not prospective_item.text) or (not next_sibling.text):
                return False
    return True


def parse_toc_entries(soup):
    parsed_toc_entries = []
    toc_items = soup.find_all(class_=is_toc_item)
    for toc_entry in toc_items:
        level = int(toc_entry['class'][0][-1:])
        soup_index = get_soup_index(soup, toc_entry)
        entry = data.ChapterTOCEntry(level, soup_index, toc_entry)
        parsed_toc_entries.append(entry)
    return parsed_toc_entries


def parse_appendix_toc_entries(soup):
    parsed_appendix_toc_entries = []
    appendix_toc_list_tags = soup.find_all(class_='appendixlist')
    for appendix_toc_listing in appendix_toc_list_tags:
        level = 4
        soup_index = get_soup_index(soup, appendix_toc_listing)
        entry = data.AppendixTOCEntry(level, soup_index, appendix_toc_listing)
        parsed_appendix_toc_entries.append(entry)
    return parsed_appendix_toc_entries


def parse_toc_content(soup):
    toc_items = soup.find_all(id=is_toc_content)
    valid_items = list(filter(is_valid_toc_content_item, toc_items))
    parsed_content_links = []
    for element in valid_items:
        soup_index = get_soup_index(soup, element)
        text = remove_trailing_footnote_text(
                get_toc_content_text(element, soup))
        item = data.TOCLinkItem(element, soup_index, text, element.contents)
        parsed_content_links.append(item)
    return parsed_content_links


def parse_appendix_toc_content(soup):
    appendices = soup.find_all(class_='appendix')
    parsed_appendix_toc_contents = []
    for appendix_tag in appendices:
        soup_index = get_soup_index(soup, appendix_tag)
        text = remove_trailing_footnote_text(
                get_appendix_toc_content_text(appendix_tag, soup))
        item = data.TOCLinkItem(
                appendix_tag, soup_index, text, appendix_tag.contents)
        parsed_appendix_toc_contents.append(item)
    return parsed_appendix_toc_contents


def get_soup_contents_between_compound_indices(soup, start, end=None):
    start_index_fragments = start.split('.')
    start_index = int(start_index_fragments[0])
    if end:
        end_index_fragments = end.split('.')
        end_index = int(end_index_fragments[0])
        return soup.contents[start_index:end_index]
    return soup.contents[start_index:]


def extract_toc_entry_contents(toc_items, soup):
    for i, item in enumerate(toc_items):
        this_soup_index = item.soup_index
        if i < len(toc_items) - 1:
            next_soup_index = toc_items[i + 1].soup_index
            item.contents = get_soup_contents_between_compound_indices(
                soup, this_soup_index, next_soup_index)
        else:
            item.contents = get_soup_contents_between_compound_indices(
                soup, this_soup_index)


def find_parent_of_index(index, items):
    # the next previous entry that has a lower level
    # should return a chapter if level == 1
    item = items[index]
    for i in range(index - 1, -1, -1):
        possible_parent = items[i]
        if possible_parent.level < item.level:
            return possible_parent
    return None


def get_content_class_for_entry(entry):
    if isinstance(entry, data.AppendixTOCEntry):
        return data.SingleAppendixArticle
    elif 'APPENDIX' in entry.text:
        return data.ChapterAppendix
    return data.level_definitions[entry.level]


def build_content_items(toc_entries):
    items = []
    for i, entry in enumerate(toc_entries):
        init_kwargs = dict(
            title=entry.text,
            contents=entry.content_link.contents,
            soup_index=entry.content_link.soup_index,
            level=entry.level,
            page_number=entry.page_number,
            toc_listing=entry,
            content_anchor=entry.content_link
        )
        ContentClass = get_content_class_for_entry(entry)
        items.append(ContentClass(**init_kwargs))
    return items


def soup_top_index(soup_index):
    return int(soup_index.split('.')[0])


def find_prev_from_index(index, items):
    # defined as prev sibling or parent
    item = items[index]
    for i in range(index - 1, -1, -1):
        possible_prev = items[i]
        if possible_prev.level <= item.level:
            return possible_prev
    return None


def link_parents_and_neighbors(content_items):
    last_index = len(content_items) - 1
    for index, item in enumerate(content_items):
        if index > 0:
            item.prev = find_prev_from_index(index, content_items)
        if index < last_index:
            item.next = content_items[index + 1]
        parent = find_parent_of_index(index, content_items)
        item.parent = parent
        if parent:
            parent.children.append(item)


def are_the_same_chapter(a, b):
    if not a or not b:
        return False
    prev_index = soup_top_index(a.soup_index)
    this_index = soup_top_index(b.soup_index)
    if (this_index - prev_index) < 4:
        return True
    elif (a.text in b.text) or (b.text in a.text):
        return True
    return False


def merge_two(a, b):
    if (a.text in b.text) or (b.text in a.text):
        text = a.text
    else:
        text = a.text + ' ' + b.text
    return data.Chapter(text=text, soup_index=a.soup_index)


def merge_adjacent_chapter_items(chapters):
    merged_chapters = []
    last_chapter = None
    while chapters:
        next_chapter = chapters.pop(0)
        if last_chapter:
            if are_the_same_chapter(last_chapter, next_chapter):
                merged = merge_two(last_chapter, next_chapter)
                merged_chapters.append(merged)
                last_chapter = None
            else:
                merged_chapters.append(last_chapter)
                last_chapter = next_chapter
        else:
            last_chapter = next_chapter
    if not chapters and last_chapter:
        merged_chapters.append(last_chapter)
    return merged_chapters


def clean_chapter_text(chapters):
    for chapter in chapters:
        text = chapter.text.split('(')[0]
        text = ':'.join(text.split(':'))
        text = ' '.join(text.split())
        text = text.strip()
        chapter.text = text.strip(':')


def should_be_excluded(chapter):
    chapter_text = chapter.text.strip().lower()
    is_empty = not bool(chapter_text)
    return is_empty or any(
        [title in chapter_text for title in CHAPTER_TITLES_TO_EXCLUDE])


def looks_like_a_chapter_link_listing(text):
    if not text:
        return False
    chunks = text.split(" ")
    return all([
        frag in chunks for frag in ("CHAPTER", '|', '–', 'PG.')
        ])


def find_chapter_page_number(chapter, chapter_elements):
    chapter_text = chapter.title.upper().split(':')[0]
    for element in chapter_elements:
        if chapter_text in element.text:
            return int(element.text.split()[-1])


def obtain_chapter_page_numbers(chapters, soup):
    master_toc = soup.find_all(
        "strong", string='MASTER TABLE OF CONTENTS')[0].parent
    next_element = master_toc.next_sibling
    search_space = 30
    chapter_elements = []
    while search_space > 0:
        if next_element.text and (
                'CHAPTER' in next_element.text) or (
                'APPENDIX' in next_element.text):
            chapter_elements.append(next_element)
        search_space -= 1
        next_element = next_element.next_sibling
    for chapter in chapters:
        chapter.page_number = find_chapter_page_number(
            chapter, chapter_elements)


def parse_chapters(soup):
    results = soup.find_all('h1')
    raw_chapters = [
        data.Chapter(
            text=result.text,
            soup_index=get_soup_index(soup, result))
        for result in results]
    chapters = merge_adjacent_chapter_items(raw_chapters)
    clean_chapter_text(chapters)
    chapters = [
        chapter for chapter in chapters
        if not should_be_excluded(chapter)]
    return chapters


def add_chapters_to_content_items(content_items, chapters, soup):
    # turn chapters into content items
    chapter_content_items = [
        data.ChapterIndex(
            title=chapter.text,
            level=0,
            soup_index=chapter.soup_index
        )
        for chapter in chapters
    ]
    obtain_chapter_page_numbers(chapter_content_items, soup)
    content_items.extend(chapter_content_items)
    return sorted(content_items, key=lambda e: e.soup_index)


def update_contents(soup, items):
    last_index = len(items) - 1
    for i, item in enumerate(items):
        if i < last_index:
            next_item = items[i + 1]
            item.contents = get_soup_contents_between_compound_indices(
                soup, item.soup_index, next_item.soup_index)
        else:
            item.contents = get_soup_contents_between_compound_indices(
                soup, item.soup_index)
        if hasattr(item, 'post_process_contents'):
            item.post_process_contents()


def write_to_json(items):
    with open('all_contents.json', 'w') as outfile:
        json.dump([item.as_dict() for item in items], outfile, indent=2)
    print("wrote JSON")


def is_footnote(id_string):
    if id_string:
        return ('footnote' in id_string) and ('-ref-' not in id_string)


def is_footnote_ref(id_string):
    if id_string:
        return 'footnote-ref' in id_string


def extract_footnotes(soup):
    footnotes = soup.find_all(
        name='li', attrs={'id': is_footnote})
    index = {}
    for footnote in footnotes:
        number = footnote['id'].split('-')[-1]
        del footnote['id']
        annotation = soup.new_tag('sup', id='footnote-{}'.format(number))
        annotation.append(number)
        footnote.insert(0, annotation)
        index[number] = footnote
        footnote.extract()
    return index


def add_footnotes_to_article(soup, content_item, footnote_index):
    footnote_refs = []
    for node in content_item.contents:
        footnote_refs.extend(
            node.find_all(name='a', attrs={'id': is_footnote_ref}))
    footnote_ids = []
    if footnote_refs:
        footnote_list = soup.new_tag('ol', **{'class': 'footnotes'})
        for ref in footnote_refs:
            number = ref['id'].split('-')[-1]
            footnote_ids.append(number)
            ref.string = '[{}]'.format(number)
            sup = ref.parent
            if sup.parent.name == 'sup' and ref.parent.name == 'sup':
                sup.parent.insert(0, ref.extract())
                sup.extract()
        for footnote_id in sorted(footnote_ids):
            footnote = footnote_index[footnote_id]
            footnote_list.append(footnote)
        content_item.contents.append(footnote_list)


def add_page_links_to_article(content_item):
    pattern = re.compile(r'PG\.?\s+(\d+)')
    page_link_path = data.global_context['prefix'] + '/page-index/'
    link_template = '<a class="page_link" href="{path}#page_{page}">{base}</a>'
    for i in range(len(content_item.contents)):
        text = str(content_item.contents[i])
        matches = list(pattern.finditer(text))
        delta = 0
        for match in matches:
            span = match.span()
            before = text[:match.start() + delta]
            after = text[match.end() + delta:]
            original_text = match.group(0)
            page_number = match.group(1)
            link_replacement = link_template.format(
                path = page_link_path, page=page_number, base=original_text)
            delta += len(link_replacement) - len(original_text)
            text = before + link_replacement + after
        content_item.contents[i] = BeautifulSoup(text, 'html.parser')


def extract_redundant_title_heading(content_item):
    first_couple_items = content_item.contents[:2]
    for item in first_couple_items:
        item_class = item.get('class', [''])[0]
        is_appendix_lettering = item_class == 'appendix'
        is_appendix_title = \
            item_class in ['appendixtitle', 'appendixtocheading']
        is_heading = item.name in ('h1', 'h2', 'h3', 'h4')
        is_title_heading_tag = is_appendix_title or is_heading
        is_title = content_item.title.lower() in item.text.lower()
        if is_appendix_lettering or (is_title_heading_tag and is_title):
            content_item.contents.remove(item)


def create_page_index(content_items):
    page_index = data.PageIndex()
    for item in content_items:
        page_index.add_listing(item)
    return page_index


def move_img_files():
    # find all the image files in the output directory
    img_file_extensions = ('.png', '.tiff', '.jpeg', '.x-emf')
    items = os.listdir(OUTPUT_DIRECTORY)
    destination_folder = os.path.join(OUTPUT_DIRECTORY, 'img')
    os.makedirs(destination_folder, exist_ok=True)
    image_files = [
        item for item in os.listdir(OUTPUT_DIRECTORY)
        if os.path.splitext(item)[-1] in img_file_extensions
    ]
    for image_file in image_files:
        from_path = os.path.join(OUTPUT_DIRECTORY, image_file)
        to_path = os.path.join(destination_folder, image_file)
        shutil.move(from_path, to_path)


def adjust_all_img_src_paths(soup):
    for img in soup.find_all('img'):
        existing_src = img['src']
        img['src'] = "/{}/{}".format(IMG_PATH, existing_src)


def save_image_file_table(content_items):
    with open('image_files.tsv', 'w') as image_table:
        for item in content_items:
            for tag in item.get_img_tags():
                image_table.write('\t'.join(tag) + '\n')
    print('Image file data written to image_files.tsv')


def soup_sorted(iterable):
    return sorted(iterable, key=lambda n: n.soup_index)


def find_first_preceding_match(target, potential_matches):
    '''We only want to produce a match if entry in the table of contents
    is in fact _before_ the content we are trying to link it to.
    '''
    for potential_match in potential_matches:
        if potential_match.soup_index < target.soup_index:
            return potential_match


def link_listing_to_content(listing, content):
    content.linked_entry = listing
    listing.content_link = content


def find_listings_with_close_key(target, lookup):
    similarity_threshold = 0.97
    target_text = target.text
    lookup_keys = tuple(lookup.keys())
    potential_matches = []
    for key in lookup_keys:
        similarity = Levenshtein.ratio(key, target_text)
        if similarity > similarity_threshold:
            potential_matches.append((similarity, key))
    if potential_matches:
        best_key = sorted(potential_matches, key=lambda n: n[0])[0][1]
        return lookup[best_key]


def link_toc_entries_to_matching_content(toc_listings, toc_targets):
    sorted_listings = soup_sorted(toc_listings)
    sorted_targets = soup_sorted(toc_targets)
    lookup = {}
    # create lists for each unique entry text key
    for listing in sorted_listings:
        if listing.text in lookup:
            lookup[listing.text].append(listing)
        else:
            lookup[listing.text] = [listing]
    all_lookup_keys = tuple(lookup.keys())
    # find toc entry based on text and pull first match
    # ignore targets with no listings.
    for target in sorted_targets:
        matched_listings = lookup.get(target.text, None)
        if not matched_listings:
            matched_listings = find_listings_with_close_key(target, lookup)
        if matched_listings:
            match = find_first_preceding_match(target, matched_listings)
            if match:
                matched_listings.remove(match)
                link_listing_to_content(match, target)


def run():
    move_img_files()
    with open(RAW_INDEX_PATH, 'r') as raw_html_input:
        soup = BeautifulSoup(raw_html_input, 'html.parser')
        adjust_all_img_src_paths(soup)
        write_prettified_raw_index(soup)
        footnote_index = extract_footnotes(soup)
        chapters = parse_chapters(soup)
        link_items = parse_toc_content(soup)
        appendix_link_items = parse_appendix_toc_content(soup)
        link_items += appendix_link_items
        toc_entries = parse_toc_entries(soup)
        appendix_toc_entries = parse_appendix_toc_entries(soup)
        toc_entries += appendix_toc_entries
        link_toc_entries_to_matching_content(toc_entries, link_items)
        usable_links = [link for link in link_items if link.linked_entry]
        sorted_toc_links = soup_sorted(usable_links)
        extract_toc_entry_contents(sorted_toc_links, soup)
        usable_sorted_toc_entries = soup_sorted(
            [entry for entry in toc_entries if entry.content_link])

        content_items = build_content_items(usable_sorted_toc_entries)
        content_items = add_chapters_to_content_items(
            content_items, chapters, soup)
        link_parents_and_neighbors(content_items)
        page_index = create_page_index(content_items)
        update_contents(soup, content_items)

        for content_item in content_items:
            add_footnotes_to_article(soup, content_item, footnote_index)
            extract_redundant_title_heading(content_item)
            add_page_links_to_article(content_item)
        write_to_json(content_items)
        # save_image_file_table(content_items)
        data.global_context.update(
            chapters=[item for item in content_items if item.level == 0],
            page_index=page_index)
        for item in content_items:
            item.write()
            print(item.get_path())
        splash_page = data.SplashPage(title='Home', level="splash")
        splash_page.write()
        print(splash_page.get_path())
        search_page = data.SearchPage(title='Search', level="search")
        search_page.write()
        print(search_page.get_path())
        page_index_page = data.PageIndexPage(
            title='Page Index', level="page-index")
        page_index_page.write()
        print(page_index_page.get_path())


if __name__ == '__main__':
    run()
