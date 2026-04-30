import { Router, type IRouter } from "express";
import healthRouter from "./health";
import experimentsRouter from "./experiments";
import templatesRouter from "./templates";

const router: IRouter = Router();

router.use(healthRouter);
router.use(experimentsRouter);
router.use(templatesRouter);

export default router;
