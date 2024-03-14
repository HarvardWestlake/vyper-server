#!/usr/bin/env python3
import asyncio
import logging
import uuid
from aiohttp import web

import vyper
from vyper.compiler import compile_code
from vyper.exceptions import VyperException

from concurrent.futures import ThreadPoolExecutor


routes = web.RouteTableDef()
headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "X-Requested-With, Content-type"
}
executor_pool = ThreadPoolExecutor(max_workers=4)

# Assuming this is a global dictionary to store compilation results
compilation_results = {}

@routes.options('/{tail:.*}')
async def options_handler(request):
    return web.Response(headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '86400',  # 24 hours
    })


@routes.get('/')
async def handle(request):
    return web.Response(text='Vyper Compiler. Version: {} \n'.format(vyper.__version__))


def _compile(data):
    # Check if 'sources' is in the data

    # Convert the sources dictionary to a list of items and grab the first one
    first_source_key, first_source_value = next(iter(data['sources'].items()))

    code = first_source_value['content']
    print(code)
    if not code:
        return {'status': 'failed', 'message': 'No "code" key supplied'}, 400
    if not isinstance(code, str):
        return {'status': 'failed', 'message': '"code" must be a non-empty string'}, 400

    try:
        out_dict = compile_code(code, ['abi', 'bytecode', 'bytecode_runtime', 'ir', 'method_identifiers'])
        out_dict['ir'] = str(out_dict['ir'])
    except VyperException as e:
        if e.col_offset and e.lineno:
            col_offset, lineno = e.col_offset, e.lineno
        elif e.annotations and len(e.annotations) > 0:
            ann = e.annotations[0]
            col_offset, lineno = ann.col_offset, ann.lineno
        else:
            col_offset, lineno = None, None
        return {
            'status': 'failed',
            'message': str(e),
            'column': col_offset,
            'line': lineno
        }, 400

    out_dict.update({'status': "success"})

    return out_dict, 200


@routes.route('OPTIONS', '/compile')
async def compile_it_options(request):
    return web.json_response(status=200, headers=headers)


@routes.post('/compile')
async def compile_it(request):
    json = await request.json()
    loop = asyncio.get_event_loop()
    out, status = await loop.run_in_executor(executor_pool, _compile, json)
    unique_id = str(uuid.uuid4())
    compilation_results[unique_id] = {'status': 'SUCCESS', 'data': out}  # 'out' should be your compilation result
    return web.json_response(unique_id, status=status, headers=headers)

@routes.get('/status/{id}')
async def check_status(request):
    comp_id = request.match_info['id']
    if comp_id in compilation_results:
        return web.Response(text="SUCCESS", status=200, headers=headers)
    else:
        return web.Response(text="NOT FOUND", status=404)

@routes.get('/artifacts/{id}')
async def get_artifacts(request):
    comp_id = request.match_info['id']
    if comp_id in compilation_results:
        return web.json_response(compilation_results[comp_id]['data'], status=200, headers=headers)
    else:
        return web.Response(text="NOT FOUND", status=404)

app = web.Application()
app.add_routes(routes)
logging.basicConfig(level=logging.DEBUG)
web.run_app(app)
