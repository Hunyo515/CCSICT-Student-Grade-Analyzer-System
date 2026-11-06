"""Separate read filters, active-term enrollment, and future class preparation."""
from flask import request,session,abort,has_request_context
from .db import query_one,query_all


def active():
    return query_one('SELECT term_id,school_year,semester,is_active,enlistment_open FROM school_terms WHERE is_active=1')


def selected():
    if not has_request_context():return active()
    if request.method!='GET':return active()
    value=request.args.get('term_filter',session.get('term_filter',''))
    if value=='all':
        session['term_filter']='all'
        return dict(term_id=None,school_year='All school years',semester='All semesters',is_active=0,is_all=True)
    if value:
        if not value.isdigit():abort(400,description='Choose a valid school-term filter.')
        term=query_one('SELECT term_id,school_year,semester,is_active,enlistment_open FROM school_terms WHERE term_id=:id',{'id':int(value)})
        if not term:abort(404)
        session['term_filter']=str(term['term_id']);return term
    term=active()
    return term or query_one('SELECT term_id,school_year,semester,is_active,enlistment_open FROM school_terms ORDER BY term_id DESC FETCH FIRST 1 ROWS ONLY')


def order(term):
    return (int(term['school_year'][:4]),{'1st Semester':1,'2nd Semester':2,'Summer':3}[term['semester']])


def enlistment():
    return query_one('SELECT term_id,school_year,semester,is_active,enlistment_open FROM school_terms WHERE enlistment_open=1')


def offering_terms():
    return query_all('SELECT term_id,school_year,semester,is_active,enlistment_open FROM school_terms WHERE is_active=1 OR enlistment_open=1 ORDER BY school_year,term_id')
