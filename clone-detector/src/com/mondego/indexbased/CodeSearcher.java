package com.mondego.indexbased;

import java.io.File;
import java.io.IOException;
import java.util.List;
import java.util.Map.Entry;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.lucene.analysis.Analyzer;
import org.apache.lucene.analysis.core.KeywordAnalyzer;
import org.apache.lucene.document.Document;
import org.apache.lucene.index.DirectoryReader;
import org.apache.lucene.index.IndexReader;
import org.apache.lucene.queryparser.classic.QueryParser;
import org.apache.lucene.search.IndexSearcher;
import org.apache.lucene.search.Query;
import org.apache.lucene.store.FSDirectory;
import org.apache.lucene.util.Version;

import com.mondego.models.QueryBlock;
import com.mondego.models.TokenInfo;
import com.mondego.noindex.CloneHelper;

public class CodeSearcher {
    private String indexDir;
    private IndexSearcher searcher;
    private IndexReader reader;
    private QueryParser queryParser;
    private String field;
    private static final Logger logger = LogManager.getLogger(CodeSearcher.class);

    public CodeSearcher(String indexDir, String field) {
        logger.info("index directory: "+ indexDir);
        this.field = field;
        this.indexDir = indexDir;
        try {
            this.reader = DirectoryReader.open(FSDirectory.open(new File(this.indexDir)));
        } catch (IOException e) {
            logger.error("cant get the reader to index dir, exiting, " + indexDir);
            e.printStackTrace();
            System.exit(1);
        }
        this.searcher = new IndexSearcher(this.reader);
        // TODO: pass  the analyzer as argument to constructor
        Analyzer analyzer = new KeywordAnalyzer();
        this.queryParser = new QueryParser(Version.LUCENE_46, this.field, analyzer);
    }

    public void search(QueryBlock queryBlock, TermSearcher termSearcher) throws IOException {
        termSearcher.setReader(this.reader);
        termSearcher.setQuerySize(queryBlock.getSize());
        termSearcher.setComputedThreshold(queryBlock.getComputedThreshold());
        int termsSeenInQuery = 0;
        StringBuilder prefixTerms = new StringBuilder();
        for (Entry<String, TokenInfo> entry : queryBlock.getPrefixMap()
                .entrySet()) {
	    Query query = null;
            try {
                prefixTerms.append(entry.getKey() + " ");
                synchronized (this) {
                    query = queryParser.parse("\"" + entry.getKey() + "\"");
                }
                termSearcher.setSearchTerm(query.toString(this.field));
                termSearcher.setFreqTerm(entry.getValue().getFrequency());
                termsSeenInQuery += entry.getValue().getFrequency();
                termSearcher.searchWithPosition(termsSeenInQuery);
            } catch (org.apache.lucene.queryparser.classic.ParseException e) {
                logger.warn("cannot parse " + entry.getKey() );
            }
        }
    }

    public CustomCollectorFwdIndex search(Document doc) throws IOException {
        CustomCollectorFwdIndex result = new CustomCollectorFwdIndex();
        Query query = null;
        try {
            synchronized (this) {
                query = queryParser.parse(doc.get("id"));
            }
            this.searcher.search(query, result);
        } catch (org.apache.lucene.queryparser.classic.ParseException e) {
            logger.warn("cannot parse (id): " + doc.get("id") + ". Ignoring this.");
        }
        return result;
    }
    
    public CustomCollectorFwdIndex search(String id) throws IOException {
        CustomCollectorFwdIndex result = new CustomCollectorFwdIndex();
        Query query = null;
        try {
            synchronized (this) {
                query = queryParser.parse(id);
            }
            this.searcher.search(query, result);
        } catch (org.apache.lucene.queryparser.classic.ParseException e) {
            logger.warn("cannot parse (" + id +"):" + id + ". Ignoring this.");
        }
        return result;
    }

    public long getFrequency(String key) {
        CustomCollectorFwdIndex result = new CustomCollectorFwdIndex();
        Query query = null;
        long frequency = -1l;
        try {
            synchronized (this) {
                query = queryParser.parse(key);
            }
            this.searcher.search(query, result);
            List<Integer> blocks = result.getBlocks();
            if (blocks.size() == 1) {
                Document document = this.getDocument(blocks.get(0));
                frequency = Long.parseLong(document.get("frequency"));
            }else{
                logger.warn("number of blocks returend by gtpm: "+blocks.size()  + ", key is: "+ key + " query: "+ query);
            }
        } catch (org.apache.lucene.queryparser.classic.ParseException e) {
            logger.warn("cannot parse (freq): " + key + ". Ignoring this.");
        } catch (NumberFormatException e) {
            logger.warn("getPosition method in CodeSearcher "
                    + e.getMessage());
        } catch (IOException e) {
            logger.error("error while getting frequency",e);
        }
        return frequency;
    }

    public Document getDocument(long docId) throws IOException {
	    try {
            return this.searcher.doc((int) docId);
        } catch (IllegalArgumentException e) {
            logger.warn(SearchManager.NODE_PREFIX + ", CodeSearcher on " + indexDir + ": invalid docId " + docId);
            return null;
        }
    }

    /**
     * @return the reader
     */
    public IndexReader getReader() {
        return reader;
    }

    /**
     * @param reader the reader to set
     */
    public void setReader(IndexReader reader) {
        this.reader = reader;
    }

    public void close() {
        try {
            this.reader.close();
        } catch (IOException e) {
                logger.warn(e.getMessage());
        }
    }
}
