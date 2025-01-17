var ALGOLIA_APP_ID = "ER4XGAZU3H";
var ALGOLIA_PUBLIC_KEY = "ad6b289aa74181fef926dc6133bfece7";
var ALGOLIA_INDEX_NAME = "test_ROADMAP";
function getParameterByName(name, url) {
  // taken from https://stackoverflow.com/a/901144/399726
  if (!url) url = window.location.href;
  name = name.replace(/[\[\]]/g, "\\$&");
  var regex = new RegExp("[?&]" + name + "(=([^&#]*)|&|#|$)"),
      results = regex.exec(url);
  if (!results) return null;
  if (!results[2]) return '';
  return decodeURIComponent(results[2].replace(/\+/g, " "));
}


function searchResultTemplate(searchResult){
  return '<li class="search-result">' + 
           '<h3 class="search-result__title">' +
            '<a href="' +
              '/' + searchResult.path + '/"' +
              'class="search-result__link">' +
                searchResult._highlightResult.title.value +
            '</a>' +
           '</h3>' +
         '</li>'
}

function searchQueryMetadataTemplate(searchData){
  return '<p class="search-metadata">' + 
            searchData.resultsCount + ' results found ' +
            'for <mark>“' + searchData.searchTerm + '”</mark>' +
         '</p>'
}

function initializeSearch() {
  var client = algoliasearch(ALGOLIA_APP_ID, ALGOLIA_PUBLIC_KEY);
  var index = client.initIndex(ALGOLIA_INDEX_NAME);
  var search_term = getParameterByName('q');
  if( search_term ){
    // from:
    //   https://www.algolia.com/doc/api-reference/api-methods/search/
    index.search({ 
      query: search_term,
      hitsPerPage: 50,
      attributesToRetrieve: [
        'title', 'heading_text', 'path', 'level', 'objectID']
      },
      function searchDone(err, content) {
        if (err) {
          console.error(err);
          return;
        }
        var resultsCount = content.hits.length;
        var metadataElement = $('.search-results__metadata');
        var metadataHTML = searchQueryMetadataTemplate({
          resultsCount: resultsCount,
          searchTerm: search_term
        });
        metadataElement.append($(metadataHTML));

        var resultsElement = $('.search-results__list');
        for (var h in content.hits) {
          var result = content.hits[h];
          var renderedResult = searchResultTemplate(result);
          resultsElement.append($(renderedResult))
      }
    });
    $('.search-form input').val(search_term);
  }

}


function handleTopPages(topPages){
  var veryTopPages = topPages.slice(1, 8);
  veryTopPages.forEach(function(page){
    var cleanedPageURL = page.url.replace("/roadmap-to-html", "");
    if(cleanedPageURL != "/"){
      $('.popular-pages__list').append(
        '<li class="popular-page"><a href="'+cleanedPageURL+'">'+page.title+'</a></li>'
      );
    }
  });
}


function pullTopPages(){
  $.getJSON(
    'https://s3.amazonaws.com/rr-roadmap-top-pages-checker/top_pages.json',
    handleTopPages
  );
}


function callByBodyDataPagePath(path, func){
  // this looks for a 'data-page-path' attribute on the body tag
  // and calls the function if the input path strictly matches the value
  // of that attribute
  var bodyPagePath = $('body').data('page-path');
  if (bodyPagePath == path){
    func();
  }
}


$(function() {
  callByBodyDataPagePath('search', initializeSearch);
  callByBodyDataPagePath('', pullTopPages);
});
