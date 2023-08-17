from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
import db_helper
import generic_helper

app = FastAPI()
inprogress_order = {}


@app.get("/")
async def read_root():
    return "Hello, World"


@app.post("/")
async def handle_request(request: Request):
    # Retrieve the JSON data from the request
    payload = await request.json()

    # Extract the necessary information from the payload
    # based on the structure of the WebhookRequest from Dialogflow
    intent = payload["queryResult"]["intent"]["displayName"]
    parameters = payload["queryResult"]["parameters"]
    output_contexts = payload["queryResult"]["outputContexts"]
    session_id = generic_helper.extract_session_id(output_contexts[0]['name'])

    intent_handler_dict = {
        'new.order': new_order,
        'add.order : ongoing-order': add_to_order,
        'remove.order : ongoing-order': remove_from_order,
        'complete.order : ongoing-order': complete_order,
        'track.order : ongoing-tracking': track_order
    }

    return intent_handler_dict[intent](parameters, session_id)


def new_order(parameters: dict, session_id: str):
    current_order = inprogress_order[session_id]
    for item in current_order:
        del current_order[item]

    inprogress_order[session_id] = current_order
    return inprogress_order[session_id]


def add_to_order(parameters: dict, session_id: str):
    food_item = parameters["food-item"]
    quantity = parameters['number']

    if len(food_item) != len(quantity):
        fulfillmentText = 'Please specify food item and quantity both. eg 2 pizza'

    else:
        quantity = tuple(quantity)
        food_item = tuple(food_item)

        new_food_dict = {key: value for key, value in zip(food_item, quantity)}

        if session_id in inprogress_order:
            current_food_dict = inprogress_order[session_id]
            current_food_dict.update(new_food_dict)
            inprogress_order[session_id] = current_food_dict

        else:
            inprogress_order[session_id] = new_food_dict

        order_str = generic_helper.get_str_from_food_dict(inprogress_order[session_id])
        fulfillmentText = f'so far you have ordered {order_str}. Do you want anything else?'

    return JSONResponse(content={
        'fulfillmentText': fulfillmentText}
    )


def complete_order(parameters: dict, session_id: str):
    if session_id not in inprogress_order:
        fulfillmentText = 'Unable to place your order. Can you place a new order please'
    else:
        order = inprogress_order[session_id]
        order_id = save_to_db(order)

        if order_id == -1:
            fulfillmentText = "Sorry , I couldn't place your order due to backend \n" \
                             "Please place new order again."

        else:
            order_total = db_helper.get_total_order_price(order_id)
            fulfillmentText = f"Awesome. We have placed your order. " \
                             f"Here is your order id # {order_id}. " \
                             f"Your order total is {order_total} which you can pay at the time of delivery!"

    del inprogress_order[session_id]

    return JSONResponse(content={
        'fulfillmentText': fulfillmentText}
    )


def save_to_db(order):
    next_order_id = db_helper.get_next_order_id()

    for food_item, quantity in order.items():
        rcode = db_helper.insert_order_item(
            food_item,
            quantity,
            next_order_id
        )

        if rcode == -1:
            return -1

    db_helper.insert_order_tracking(next_order_id, 'in progress')
    return next_order_id


def track_order(parameters: dict, session_id: str):
    order_id = int(parameters['number'])

    order_status = db_helper.get_order_status(order_id)
    if order_status:
        fulfillmentText = f'status for order_id {order_id} is : {order_status}'
    else:
        fulfillmentText = f'status for order_id {order_id} is not found'

    return JSONResponse(content={
        'fulfillmentText': fulfillmentText}
    )


def remove_from_order(parameters: dict, session_id: str):
    if session_id not in inprogress_order:
        return JSONResponse(content={
            "fulfillmentText": "I'm having a trouble finding your order. Sorry! Can you place a new order please?"
        })
    current_order = inprogress_order[session_id]
    food_item = parameters['food-item']

    removed_item = []
    not_exist = []

    for item in food_item:
        if item not in current_order:
            not_exist.append(item)
        else:
            removed_item.append(item)
            del current_order[item]

    if len(removed_item) > 0:
        fulfillmentText = f'Removed {",".join(removed_item)} from your order'

    if len(not_exist) > 0:
        fulfillmentText = f'No such items {",".join(not_exist)} exists in your order!'

    if len(current_order.keys()) == 0:
        fulfillmentText = 'Your order is empty!'
    else:
        order_str = generic_helper.get_str_from_food_dict(current_order)
        fulfillmentText += f" Here is what is left in your order: {order_str}"


    return JSONResponse(content={
        "fulfillmentText": fulfillmentText
    })
