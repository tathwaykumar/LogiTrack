--
-- PostgreSQL database dump
--

\restrict pcBSqycYvei27yYu0KA3BR7K4ecBwDnZMbbT7eg93EgcoCnJEKXXjtEy312kQko

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

-- Started on 2026-09-03 22:16:23

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 224 (class 1259 OID 16424)
-- Name: customer; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.customer (
    customer_id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(100) NOT NULL,
    phone character varying(20),
    address character varying(255),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.customer OWNER TO postgres;

--
-- TOC entry 223 (class 1259 OID 16423)
-- Name: customer_customer_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.customer_customer_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.customer_customer_id_seq OWNER TO postgres;

--
-- TOC entry 5235 (class 0 OID 0)
-- Dependencies: 223
-- Name: customer_customer_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.customer_customer_id_seq OWNED BY public.customer.customer_id;


--
-- TOC entry 247 (class 1259 OID 16668)
-- Name: delivery; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.delivery (
    delivery_id integer NOT NULL,
    shipment_id integer NOT NULL,
    driver_id integer NOT NULL,
    delivery_date timestamp without time zone,
    delivery_status character varying(30) DEFAULT 'PENDING'::character varying NOT NULL,
    delivery_address character varying(255) NOT NULL,
    CONSTRAINT chk_delivery_status CHECK (((delivery_status)::text = ANY ((ARRAY['PENDING'::character varying, 'OUT_FOR_DELIVERY'::character varying, 'DELIVERED'::character varying, 'FAILED'::character varying, 'CANCELLED'::character varying])::text[])))
);


ALTER TABLE public.delivery OWNER TO postgres;

--
-- TOC entry 246 (class 1259 OID 16667)
-- Name: delivery_delivery_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.delivery_delivery_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.delivery_delivery_id_seq OWNER TO postgres;

--
-- TOC entry 5236 (class 0 OID 0)
-- Dependencies: 246
-- Name: delivery_delivery_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.delivery_delivery_id_seq OWNED BY public.delivery.delivery_id;


--
-- TOC entry 227 (class 1259 OID 16459)
-- Name: driver; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.driver (
    employee_id integer NOT NULL,
    license_no character varying(50) NOT NULL,
    license_expiry date NOT NULL,
    availability_status character varying(30) DEFAULT 'AVAILABLE'::character varying
);


ALTER TABLE public.driver OWNER TO postgres;

--
-- TOC entry 231 (class 1259 OID 16491)
-- Name: driver_vehicle_assignment; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.driver_vehicle_assignment (
    assignment_id integer NOT NULL,
    driver_id integer NOT NULL,
    vehicle_id integer NOT NULL,
    assigned_from date NOT NULL,
    assigned_to date,
    CONSTRAINT chk_assignment_dates CHECK (((assigned_to IS NULL) OR (assigned_to >= assigned_from)))
);


ALTER TABLE public.driver_vehicle_assignment OWNER TO postgres;

--
-- TOC entry 230 (class 1259 OID 16490)
-- Name: driver_vehicle_assignment_assignment_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.driver_vehicle_assignment_assignment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.driver_vehicle_assignment_assignment_id_seq OWNER TO postgres;

--
-- TOC entry 5237 (class 0 OID 0)
-- Dependencies: 230
-- Name: driver_vehicle_assignment_assignment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.driver_vehicle_assignment_assignment_id_seq OWNED BY public.driver_vehicle_assignment.assignment_id;


--
-- TOC entry 226 (class 1259 OID 16442)
-- Name: employee; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.employee (
    employee_id integer NOT NULL,
    user_id integer,
    name character varying(100) NOT NULL,
    phone character varying(20),
    department character varying(50),
    hire_date date,
    salary numeric(10,2),
    employment_status character varying(30) DEFAULT 'ACTIVE'::character varying,
    CONSTRAINT chk_employee_salary CHECK (((salary IS NULL) OR (salary >= (0)::numeric)))
);


ALTER TABLE public.employee OWNER TO postgres;

--
-- TOC entry 225 (class 1259 OID 16441)
-- Name: employee_employee_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.employee_employee_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.employee_employee_id_seq OWNER TO postgres;

--
-- TOC entry 5238 (class 0 OID 0)
-- Dependencies: 225
-- Name: employee_employee_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.employee_employee_id_seq OWNED BY public.employee.employee_id;


--
-- TOC entry 236 (class 1259 OID 16542)
-- Name: inventory; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.inventory (
    warehouse_id integer NOT NULL,
    product_id integer NOT NULL,
    quantity integer DEFAULT 0 NOT NULL,
    reorder_level integer DEFAULT 0 NOT NULL,
    last_updated timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_inventory_quantity CHECK ((quantity >= 0)),
    CONSTRAINT chk_inventory_reorder CHECK ((reorder_level >= 0))
);


ALTER TABLE public.inventory OWNER TO postgres;

--
-- TOC entry 251 (class 1259 OID 16719)
-- Name: invoice; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.invoice (
    invoice_id integer NOT NULL,
    order_id integer NOT NULL,
    invoice_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    subtotal numeric(12,2) NOT NULL,
    tax numeric(12,2) DEFAULT 0 NOT NULL,
    total_amount numeric(12,2) NOT NULL,
    invoice_status character varying(30) DEFAULT 'ISSUED'::character varying NOT NULL,
    CONSTRAINT chk_invoice_calculation CHECK ((total_amount = (subtotal + tax))),
    CONSTRAINT chk_invoice_subtotal CHECK ((subtotal >= (0)::numeric)),
    CONSTRAINT chk_invoice_tax CHECK ((tax >= (0)::numeric)),
    CONSTRAINT chk_invoice_total CHECK ((total_amount >= (0)::numeric))
);


ALTER TABLE public.invoice OWNER TO postgres;

--
-- TOC entry 250 (class 1259 OID 16718)
-- Name: invoice_invoice_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.invoice_invoice_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.invoice_invoice_id_seq OWNER TO postgres;

--
-- TOC entry 5239 (class 0 OID 0)
-- Dependencies: 250
-- Name: invoice_invoice_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.invoice_invoice_id_seq OWNED BY public.invoice.invoice_id;


--
-- TOC entry 239 (class 1259 OID 16585)
-- Name: order_item; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.order_item (
    order_id integer NOT NULL,
    product_id integer NOT NULL,
    quantity integer NOT NULL,
    unit_price numeric(10,2) NOT NULL,
    CONSTRAINT chk_order_item_price CHECK ((unit_price >= (0)::numeric)),
    CONSTRAINT chk_order_item_quantity CHECK ((quantity > 0))
);


ALTER TABLE public.order_item OWNER TO postgres;

--
-- TOC entry 238 (class 1259 OID 16567)
-- Name: orders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.orders (
    order_id integer NOT NULL,
    customer_id integer NOT NULL,
    order_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    order_status character varying(30) DEFAULT 'PENDING'::character varying NOT NULL,
    shipping_address character varying(255) NOT NULL,
    CONSTRAINT chk_order_status CHECK (((order_status)::text = ANY ((ARRAY['PENDING'::character varying, 'CONFIRMED'::character varying, 'PROCESSING'::character varying, 'SHIPPED'::character varying, 'DELIVERED'::character varying, 'CANCELLED'::character varying])::text[])))
);


ALTER TABLE public.orders OWNER TO postgres;

--
-- TOC entry 237 (class 1259 OID 16566)
-- Name: orders_order_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.orders_order_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.orders_order_id_seq OWNER TO postgres;

--
-- TOC entry 5240 (class 0 OID 0)
-- Dependencies: 237
-- Name: orders_order_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.orders_order_id_seq OWNED BY public.orders.order_id;


--
-- TOC entry 249 (class 1259 OID 16694)
-- Name: payment; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.payment (
    payment_id integer NOT NULL,
    order_id integer NOT NULL,
    amount numeric(12,2) NOT NULL,
    payment_method character varying(30) NOT NULL,
    payment_status character varying(30) DEFAULT 'PENDING'::character varying NOT NULL,
    payment_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    transaction_reference character varying(100),
    CONSTRAINT chk_payment_amount CHECK ((amount > (0)::numeric)),
    CONSTRAINT chk_payment_status CHECK (((payment_status)::text = ANY ((ARRAY['PENDING'::character varying, 'SUCCESS'::character varying, 'FAILED'::character varying, 'REFUNDED'::character varying])::text[])))
);


ALTER TABLE public.payment OWNER TO postgres;

--
-- TOC entry 248 (class 1259 OID 16693)
-- Name: payment_payment_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.payment_payment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.payment_payment_id_seq OWNER TO postgres;

--
-- TOC entry 5241 (class 0 OID 0)
-- Dependencies: 248
-- Name: payment_payment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.payment_payment_id_seq OWNED BY public.payment.payment_id;


--
-- TOC entry 235 (class 1259 OID 16531)
-- Name: product; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.product (
    product_id integer NOT NULL,
    product_name character varying(100) NOT NULL,
    category character varying(50),
    unit_price numeric(10,2) NOT NULL,
    weight numeric(10,2),
    description character varying(255),
    CONSTRAINT chk_product_price CHECK ((unit_price >= (0)::numeric)),
    CONSTRAINT chk_product_weight CHECK (((weight IS NULL) OR (weight > (0)::numeric)))
);


ALTER TABLE public.product OWNER TO postgres;

--
-- TOC entry 234 (class 1259 OID 16530)
-- Name: product_product_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.product_product_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.product_product_id_seq OWNER TO postgres;

--
-- TOC entry 5242 (class 0 OID 0)
-- Dependencies: 234
-- Name: product_product_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.product_product_id_seq OWNED BY public.product.product_id;


--
-- TOC entry 220 (class 1259 OID 16390)
-- Name: role; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.role (
    role_id integer NOT NULL,
    role_name character varying(50) NOT NULL,
    description character varying(255)
);


ALTER TABLE public.role OWNER TO postgres;

--
-- TOC entry 219 (class 1259 OID 16389)
-- Name: role_role_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.role_role_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.role_role_id_seq OWNER TO postgres;

--
-- TOC entry 5243 (class 0 OID 0)
-- Dependencies: 219
-- Name: role_role_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.role_role_id_seq OWNED BY public.role.role_id;


--
-- TOC entry 241 (class 1259 OID 16607)
-- Name: route; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.route (
    route_id integer NOT NULL,
    route_name character varying(100) NOT NULL,
    source character varying(100) NOT NULL,
    destination character varying(100) NOT NULL,
    distance_km numeric(10,2) NOT NULL,
    estimated_duration interval,
    route_status character varying(30) DEFAULT 'ACTIVE'::character varying,
    CONSTRAINT chk_route_distance CHECK ((distance_km > (0)::numeric))
);


ALTER TABLE public.route OWNER TO postgres;

--
-- TOC entry 240 (class 1259 OID 16606)
-- Name: route_route_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.route_route_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.route_route_id_seq OWNER TO postgres;

--
-- TOC entry 5244 (class 0 OID 0)
-- Dependencies: 240
-- Name: route_route_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.route_route_id_seq OWNED BY public.route.route_id;


--
-- TOC entry 243 (class 1259 OID 16621)
-- Name: shipment; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.shipment (
    shipment_id integer NOT NULL,
    order_id integer NOT NULL,
    warehouse_id integer NOT NULL,
    route_id integer NOT NULL,
    shipment_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    estimated_delivery timestamp without time zone,
    actual_delivery timestamp without time zone,
    shipment_status character varying(30) DEFAULT 'CREATED'::character varying NOT NULL,
    CONSTRAINT chk_shipment_dates CHECK (((actual_delivery IS NULL) OR (actual_delivery >= shipment_date))),
    CONSTRAINT chk_shipment_status CHECK (((shipment_status)::text = ANY ((ARRAY['CREATED'::character varying, 'PICKED_UP'::character varying, 'IN_TRANSIT'::character varying, 'OUT_FOR_DELIVERY'::character varying, 'DELIVERED'::character varying, 'CANCELLED'::character varying])::text[])))
);


ALTER TABLE public.shipment OWNER TO postgres;

--
-- TOC entry 252 (class 1259 OID 16746)
-- Name: shipment_item; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.shipment_item (
    shipment_id integer NOT NULL,
    order_id integer NOT NULL,
    product_id integer NOT NULL,
    quantity integer NOT NULL,
    CONSTRAINT chk_shipment_item_quantity CHECK ((quantity > 0))
);


ALTER TABLE public.shipment_item OWNER TO postgres;

--
-- TOC entry 242 (class 1259 OID 16620)
-- Name: shipment_shipment_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.shipment_shipment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.shipment_shipment_id_seq OWNER TO postgres;

--
-- TOC entry 5245 (class 0 OID 0)
-- Dependencies: 242
-- Name: shipment_shipment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.shipment_shipment_id_seq OWNED BY public.shipment.shipment_id;


--
-- TOC entry 245 (class 1259 OID 16652)
-- Name: shipment_tracking; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.shipment_tracking (
    tracking_id integer NOT NULL,
    shipment_id integer NOT NULL,
    status character varying(50) NOT NULL,
    location character varying(150),
    tracking_timestamp timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    remarks character varying(255)
);


ALTER TABLE public.shipment_tracking OWNER TO postgres;

--
-- TOC entry 244 (class 1259 OID 16651)
-- Name: shipment_tracking_tracking_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.shipment_tracking_tracking_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.shipment_tracking_tracking_id_seq OWNER TO postgres;

--
-- TOC entry 5246 (class 0 OID 0)
-- Dependencies: 244
-- Name: shipment_tracking_tracking_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.shipment_tracking_tracking_id_seq OWNED BY public.shipment_tracking.tracking_id;


--
-- TOC entry 222 (class 1259 OID 16401)
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    user_id integer NOT NULL,
    role_id integer NOT NULL,
    username character varying(50) NOT NULL,
    email character varying(100) NOT NULL,
    password_hash character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    is_active boolean DEFAULT true
);


ALTER TABLE public.users OWNER TO postgres;

--
-- TOC entry 221 (class 1259 OID 16400)
-- Name: users_user_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_user_id_seq OWNER TO postgres;

--
-- TOC entry 5247 (class 0 OID 0)
-- Dependencies: 221
-- Name: users_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_user_id_seq OWNED BY public.users.user_id;


--
-- TOC entry 229 (class 1259 OID 16476)
-- Name: vehicle; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.vehicle (
    vehicle_id integer NOT NULL,
    registration_no character varying(30) NOT NULL,
    vehicle_type character varying(50) NOT NULL,
    capacity numeric(10,2) NOT NULL,
    fuel_type character varying(30),
    status character varying(30) DEFAULT 'ACTIVE'::character varying,
    purchase_date date,
    CONSTRAINT chk_vehicle_capacity CHECK ((capacity > (0)::numeric))
);


ALTER TABLE public.vehicle OWNER TO postgres;

--
-- TOC entry 228 (class 1259 OID 16475)
-- Name: vehicle_vehicle_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.vehicle_vehicle_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.vehicle_vehicle_id_seq OWNER TO postgres;

--
-- TOC entry 5248 (class 0 OID 0)
-- Dependencies: 228
-- Name: vehicle_vehicle_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.vehicle_vehicle_id_seq OWNED BY public.vehicle.vehicle_id;


--
-- TOC entry 233 (class 1259 OID 16513)
-- Name: warehouse; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.warehouse (
    warehouse_id integer NOT NULL,
    warehouse_name character varying(100) NOT NULL,
    address character varying(255) NOT NULL,
    city character varying(50) NOT NULL,
    capacity numeric(12,2),
    manager_employee_id integer,
    status character varying(30) DEFAULT 'ACTIVE'::character varying,
    CONSTRAINT chk_warehouse_capacity CHECK (((capacity IS NULL) OR (capacity > (0)::numeric)))
);


ALTER TABLE public.warehouse OWNER TO postgres;

--
-- TOC entry 232 (class 1259 OID 16512)
-- Name: warehouse_warehouse_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.warehouse_warehouse_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.warehouse_warehouse_id_seq OWNER TO postgres;

--
-- TOC entry 5249 (class 0 OID 0)
-- Dependencies: 232
-- Name: warehouse_warehouse_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.warehouse_warehouse_id_seq OWNED BY public.warehouse.warehouse_id;


--
-- TOC entry 4946 (class 2604 OID 16427)
-- Name: customer customer_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customer ALTER COLUMN customer_id SET DEFAULT nextval('public.customer_customer_id_seq'::regclass);


--
-- TOC entry 4970 (class 2604 OID 16671)
-- Name: delivery delivery_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.delivery ALTER COLUMN delivery_id SET DEFAULT nextval('public.delivery_delivery_id_seq'::regclass);


--
-- TOC entry 4953 (class 2604 OID 16494)
-- Name: driver_vehicle_assignment assignment_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.driver_vehicle_assignment ALTER COLUMN assignment_id SET DEFAULT nextval('public.driver_vehicle_assignment_assignment_id_seq'::regclass);


--
-- TOC entry 4948 (class 2604 OID 16445)
-- Name: employee employee_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employee ALTER COLUMN employee_id SET DEFAULT nextval('public.employee_employee_id_seq'::regclass);


--
-- TOC entry 4975 (class 2604 OID 16722)
-- Name: invoice invoice_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.invoice ALTER COLUMN invoice_id SET DEFAULT nextval('public.invoice_invoice_id_seq'::regclass);


--
-- TOC entry 4960 (class 2604 OID 16570)
-- Name: orders order_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders ALTER COLUMN order_id SET DEFAULT nextval('public.orders_order_id_seq'::regclass);


--
-- TOC entry 4972 (class 2604 OID 16697)
-- Name: payment payment_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payment ALTER COLUMN payment_id SET DEFAULT nextval('public.payment_payment_id_seq'::regclass);


--
-- TOC entry 4956 (class 2604 OID 16534)
-- Name: product product_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.product ALTER COLUMN product_id SET DEFAULT nextval('public.product_product_id_seq'::regclass);


--
-- TOC entry 4942 (class 2604 OID 16393)
-- Name: role role_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.role ALTER COLUMN role_id SET DEFAULT nextval('public.role_role_id_seq'::regclass);


--
-- TOC entry 4963 (class 2604 OID 16610)
-- Name: route route_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.route ALTER COLUMN route_id SET DEFAULT nextval('public.route_route_id_seq'::regclass);


--
-- TOC entry 4965 (class 2604 OID 16624)
-- Name: shipment shipment_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment ALTER COLUMN shipment_id SET DEFAULT nextval('public.shipment_shipment_id_seq'::regclass);


--
-- TOC entry 4968 (class 2604 OID 16655)
-- Name: shipment_tracking tracking_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment_tracking ALTER COLUMN tracking_id SET DEFAULT nextval('public.shipment_tracking_tracking_id_seq'::regclass);


--
-- TOC entry 4943 (class 2604 OID 16404)
-- Name: users user_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users ALTER COLUMN user_id SET DEFAULT nextval('public.users_user_id_seq'::regclass);


--
-- TOC entry 4951 (class 2604 OID 16479)
-- Name: vehicle vehicle_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vehicle ALTER COLUMN vehicle_id SET DEFAULT nextval('public.vehicle_vehicle_id_seq'::regclass);


--
-- TOC entry 4954 (class 2604 OID 16516)
-- Name: warehouse warehouse_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warehouse ALTER COLUMN warehouse_id SET DEFAULT nextval('public.warehouse_warehouse_id_seq'::regclass);


--
-- TOC entry 5012 (class 2606 OID 16433)
-- Name: customer customer_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customer
    ADD CONSTRAINT customer_pkey PRIMARY KEY (customer_id);


--
-- TOC entry 5014 (class 2606 OID 16435)
-- Name: customer customer_user_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customer
    ADD CONSTRAINT customer_user_id_key UNIQUE (user_id);


--
-- TOC entry 5046 (class 2606 OID 16680)
-- Name: delivery delivery_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.delivery
    ADD CONSTRAINT delivery_pkey PRIMARY KEY (delivery_id);


--
-- TOC entry 5048 (class 2606 OID 16682)
-- Name: delivery delivery_shipment_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.delivery
    ADD CONSTRAINT delivery_shipment_id_key UNIQUE (shipment_id);


--
-- TOC entry 5020 (class 2606 OID 16469)
-- Name: driver driver_license_no_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.driver
    ADD CONSTRAINT driver_license_no_key UNIQUE (license_no);


--
-- TOC entry 5022 (class 2606 OID 16467)
-- Name: driver driver_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.driver
    ADD CONSTRAINT driver_pkey PRIMARY KEY (employee_id);


--
-- TOC entry 5028 (class 2606 OID 16501)
-- Name: driver_vehicle_assignment driver_vehicle_assignment_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.driver_vehicle_assignment
    ADD CONSTRAINT driver_vehicle_assignment_pkey PRIMARY KEY (assignment_id);


--
-- TOC entry 5016 (class 2606 OID 16451)
-- Name: employee employee_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employee
    ADD CONSTRAINT employee_pkey PRIMARY KEY (employee_id);


--
-- TOC entry 5018 (class 2606 OID 16453)
-- Name: employee employee_user_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employee
    ADD CONSTRAINT employee_user_id_key UNIQUE (user_id);


--
-- TOC entry 5034 (class 2606 OID 16555)
-- Name: inventory inventory_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT inventory_pkey PRIMARY KEY (warehouse_id, product_id);


--
-- TOC entry 5056 (class 2606 OID 16739)
-- Name: invoice invoice_order_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.invoice
    ADD CONSTRAINT invoice_order_id_key UNIQUE (order_id);


--
-- TOC entry 5058 (class 2606 OID 16737)
-- Name: invoice invoice_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.invoice
    ADD CONSTRAINT invoice_pkey PRIMARY KEY (invoice_id);


--
-- TOC entry 5038 (class 2606 OID 16595)
-- Name: order_item order_item_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_item
    ADD CONSTRAINT order_item_pkey PRIMARY KEY (order_id, product_id);


--
-- TOC entry 5036 (class 2606 OID 16579)
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (order_id);


--
-- TOC entry 5050 (class 2606 OID 16710)
-- Name: payment payment_order_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payment
    ADD CONSTRAINT payment_order_id_key UNIQUE (order_id);


--
-- TOC entry 5052 (class 2606 OID 16708)
-- Name: payment payment_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payment
    ADD CONSTRAINT payment_pkey PRIMARY KEY (payment_id);


--
-- TOC entry 5054 (class 2606 OID 16712)
-- Name: payment payment_transaction_reference_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payment
    ADD CONSTRAINT payment_transaction_reference_key UNIQUE (transaction_reference);


--
-- TOC entry 5032 (class 2606 OID 16541)
-- Name: product product_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.product
    ADD CONSTRAINT product_pkey PRIMARY KEY (product_id);


--
-- TOC entry 5002 (class 2606 OID 16397)
-- Name: role role_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.role
    ADD CONSTRAINT role_pkey PRIMARY KEY (role_id);


--
-- TOC entry 5004 (class 2606 OID 16399)
-- Name: role role_role_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.role
    ADD CONSTRAINT role_role_name_key UNIQUE (role_name);


--
-- TOC entry 5040 (class 2606 OID 16619)
-- Name: route route_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.route
    ADD CONSTRAINT route_pkey PRIMARY KEY (route_id);


--
-- TOC entry 5060 (class 2606 OID 16755)
-- Name: shipment_item shipment_item_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment_item
    ADD CONSTRAINT shipment_item_pkey PRIMARY KEY (shipment_id, product_id);


--
-- TOC entry 5042 (class 2606 OID 16635)
-- Name: shipment shipment_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment
    ADD CONSTRAINT shipment_pkey PRIMARY KEY (shipment_id);


--
-- TOC entry 5044 (class 2606 OID 16661)
-- Name: shipment_tracking shipment_tracking_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment_tracking
    ADD CONSTRAINT shipment_tracking_pkey PRIMARY KEY (tracking_id);


--
-- TOC entry 5006 (class 2606 OID 16417)
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- TOC entry 5008 (class 2606 OID 16413)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- TOC entry 5010 (class 2606 OID 16415)
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- TOC entry 5024 (class 2606 OID 16487)
-- Name: vehicle vehicle_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vehicle
    ADD CONSTRAINT vehicle_pkey PRIMARY KEY (vehicle_id);


--
-- TOC entry 5026 (class 2606 OID 16489)
-- Name: vehicle vehicle_registration_no_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vehicle
    ADD CONSTRAINT vehicle_registration_no_key UNIQUE (registration_no);


--
-- TOC entry 5030 (class 2606 OID 16524)
-- Name: warehouse warehouse_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warehouse
    ADD CONSTRAINT warehouse_pkey PRIMARY KEY (warehouse_id);


--
-- TOC entry 5065 (class 2606 OID 16502)
-- Name: driver_vehicle_assignment fk_assignment_driver; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.driver_vehicle_assignment
    ADD CONSTRAINT fk_assignment_driver FOREIGN KEY (driver_id) REFERENCES public.driver(employee_id);


--
-- TOC entry 5066 (class 2606 OID 16507)
-- Name: driver_vehicle_assignment fk_assignment_vehicle; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.driver_vehicle_assignment
    ADD CONSTRAINT fk_assignment_vehicle FOREIGN KEY (vehicle_id) REFERENCES public.vehicle(vehicle_id);


--
-- TOC entry 5062 (class 2606 OID 16436)
-- Name: customer fk_customer_user; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customer
    ADD CONSTRAINT fk_customer_user FOREIGN KEY (user_id) REFERENCES public.users(user_id);


--
-- TOC entry 5077 (class 2606 OID 16688)
-- Name: delivery fk_delivery_driver; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.delivery
    ADD CONSTRAINT fk_delivery_driver FOREIGN KEY (driver_id) REFERENCES public.driver(employee_id);


--
-- TOC entry 5078 (class 2606 OID 16683)
-- Name: delivery fk_delivery_shipment; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.delivery
    ADD CONSTRAINT fk_delivery_shipment FOREIGN KEY (shipment_id) REFERENCES public.shipment(shipment_id);


--
-- TOC entry 5064 (class 2606 OID 16470)
-- Name: driver fk_driver_employee; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.driver
    ADD CONSTRAINT fk_driver_employee FOREIGN KEY (employee_id) REFERENCES public.employee(employee_id);


--
-- TOC entry 5063 (class 2606 OID 16454)
-- Name: employee fk_employee_user; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employee
    ADD CONSTRAINT fk_employee_user FOREIGN KEY (user_id) REFERENCES public.users(user_id);


--
-- TOC entry 5068 (class 2606 OID 16561)
-- Name: inventory fk_inventory_product; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT fk_inventory_product FOREIGN KEY (product_id) REFERENCES public.product(product_id);


--
-- TOC entry 5069 (class 2606 OID 16556)
-- Name: inventory fk_inventory_warehouse; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT fk_inventory_warehouse FOREIGN KEY (warehouse_id) REFERENCES public.warehouse(warehouse_id);


--
-- TOC entry 5080 (class 2606 OID 16740)
-- Name: invoice fk_invoice_order; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.invoice
    ADD CONSTRAINT fk_invoice_order FOREIGN KEY (order_id) REFERENCES public.orders(order_id);


--
-- TOC entry 5070 (class 2606 OID 16580)
-- Name: orders fk_order_customer; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_order_customer FOREIGN KEY (customer_id) REFERENCES public.customer(customer_id);


--
-- TOC entry 5071 (class 2606 OID 16596)
-- Name: order_item fk_order_item_order; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_item
    ADD CONSTRAINT fk_order_item_order FOREIGN KEY (order_id) REFERENCES public.orders(order_id);


--
-- TOC entry 5072 (class 2606 OID 16601)
-- Name: order_item fk_order_item_product; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_item
    ADD CONSTRAINT fk_order_item_product FOREIGN KEY (product_id) REFERENCES public.product(product_id);


--
-- TOC entry 5079 (class 2606 OID 16713)
-- Name: payment fk_payment_order; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payment
    ADD CONSTRAINT fk_payment_order FOREIGN KEY (order_id) REFERENCES public.orders(order_id);


--
-- TOC entry 5081 (class 2606 OID 16761)
-- Name: shipment_item fk_shipment_item_order_item; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment_item
    ADD CONSTRAINT fk_shipment_item_order_item FOREIGN KEY (order_id, product_id) REFERENCES public.order_item(order_id, product_id);


--
-- TOC entry 5082 (class 2606 OID 16756)
-- Name: shipment_item fk_shipment_item_shipment; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment_item
    ADD CONSTRAINT fk_shipment_item_shipment FOREIGN KEY (shipment_id) REFERENCES public.shipment(shipment_id);


--
-- TOC entry 5073 (class 2606 OID 16636)
-- Name: shipment fk_shipment_order; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment
    ADD CONSTRAINT fk_shipment_order FOREIGN KEY (order_id) REFERENCES public.orders(order_id);


--
-- TOC entry 5074 (class 2606 OID 16646)
-- Name: shipment fk_shipment_route; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment
    ADD CONSTRAINT fk_shipment_route FOREIGN KEY (route_id) REFERENCES public.route(route_id);


--
-- TOC entry 5075 (class 2606 OID 16641)
-- Name: shipment fk_shipment_warehouse; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment
    ADD CONSTRAINT fk_shipment_warehouse FOREIGN KEY (warehouse_id) REFERENCES public.warehouse(warehouse_id);


--
-- TOC entry 5076 (class 2606 OID 16662)
-- Name: shipment_tracking fk_tracking_shipment; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipment_tracking
    ADD CONSTRAINT fk_tracking_shipment FOREIGN KEY (shipment_id) REFERENCES public.shipment(shipment_id);


--
-- TOC entry 5061 (class 2606 OID 16418)
-- Name: users fk_user_role; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_user_role FOREIGN KEY (role_id) REFERENCES public.role(role_id);


--
-- TOC entry 5067 (class 2606 OID 16525)
-- Name: warehouse fk_warehouse_manager; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warehouse
    ADD CONSTRAINT fk_warehouse_manager FOREIGN KEY (manager_employee_id) REFERENCES public.employee(employee_id);


-- Completed on 2026-09-03 22:16:24

--
-- PostgreSQL database dump complete
--

\unrestrict pcBSqycYvei27yYu0KA3BR7K4ecBwDnZMbbT7eg93EgcoCnJEKXXjtEy312kQko

